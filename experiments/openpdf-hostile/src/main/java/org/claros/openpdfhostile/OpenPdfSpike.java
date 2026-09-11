package org.claros.openpdfhostile;

import org.openpdf.text.Document;
import org.openpdf.text.DocumentException;
import org.openpdf.text.Element;
import org.openpdf.text.Font;
import org.openpdf.text.PageSize;
import org.openpdf.text.Paragraph;
import org.openpdf.text.Phrase;
import org.openpdf.text.Rectangle;
import org.openpdf.text.pdf.BaseFont;
import org.openpdf.text.pdf.ColumnText;
import org.openpdf.text.pdf.PdfContentByte;
import org.openpdf.text.pdf.PdfImportedPage;
import org.openpdf.text.pdf.PdfName;
import org.openpdf.text.pdf.PdfNumber;
import org.openpdf.text.pdf.PdfPageEventHelper;
import org.openpdf.text.pdf.PdfReader;
import org.openpdf.text.pdf.PdfStamper;
import org.openpdf.text.pdf.PdfWriter;

import java.awt.Color;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public final class OpenPdfSpike {
    public static final String CONTINUATION_QUESTION_ID = "HOSTILE-LONG-001";
    public static final String CONTINUATION_WORKSHEET_TITLE =
            "Claros hostile fixture: long-multiline-answer";
    public static final String CONTINUATION_SOURCE_PAGE = "Source page 1";
    public static final String CONTINUATION_QUESTION =
            "Explain how the evidence supports the conclusion without changing the approved wording.";
    public static final String CONTINUATION_ANSWER = buildLongAnswer();

    private final Map<FontKind, Path> fonts;

    public OpenPdfSpike(Map<FontKind, Path> fonts) {
        this.fonts = fonts;
    }

    public OpenResult process(FixtureSpec spec, Path source, Path derivative)
            throws IOException, DocumentException {
        byte[] sourceBytes = Files.readAllBytes(source);
        byte[] password = spec.encrypted()
                ? spec.ownerPassword().getBytes(StandardCharsets.UTF_8)
                : new byte[0];
        PdfReader reader = new PdfReader(sourceBytes, password);
        boolean readerRebuilt = reader.isRebuilt();
        boolean incrementalAppend = !readerRebuilt;
        List<PhysicalPlacement> placements = createPlacements(spec, reader);
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        int continuationPages = 0;
        try (PdfStamper stamper = new PdfStamper(reader, output, null, incrementalAppend)) {
            // The harness owns the complete physical transform. OpenPDF's implicit
            // rotated-content adjustment is deliberately disabled.
            stamper.setRotateContents(false);
            stamper.setUpdateMetadata(false);
            stamper.setUpdateDocInfo(false);
            if (!incrementalAppend) {
                // A rebuilt xref cannot be stamped incrementally. In the full-rewrite
                // fallback, explicitly replace OpenPDF's generated info values with
                // the source dictionary so preservation remains machine-checkable.
                stamper.setInfoDictionary(reader.getInfo());
            }
            if (spec.encrypted() && !incrementalAppend) {
                stamper.setEncryption(
                        spec.userPassword().getBytes(StandardCharsets.UTF_8),
                        spec.ownerPassword().getBytes(StandardCharsets.UTF_8),
                        reader.getPermissions(),
                        reader.getCryptoMode());
            }
            for (PhysicalPlacement placement : placements) {
                overlay(stamper, reader, placement);
            }
            if (spec.continuation()) {
                byte[] continuation = createContinuationPdf();
                try (PdfReader continuationReader = new PdfReader(continuation)) {
                    continuationPages = continuationReader.getNumberOfPages();
                    appendContinuation(stamper, reader.getNumberOfPages(), continuationReader);
                }
            }
        } finally {
            reader.close();
        }
        byte[] derivativeBytes = output.toByteArray();
        if (derivativeBytes.length == 0) {
            throw new IOException("OpenPDF emitted no derivative bytes");
        }
        Files.createDirectories(derivative.getParent());
        Files.write(derivative, derivativeBytes);
        return new OpenResult(
                derivative,
                List.copyOf(placements),
                continuationPages,
                readerRebuilt,
                incrementalAppend,
                FontAssets.digest(derivative));
    }

    public OpenReadResult probeOpen(FixtureSpec spec, Path source) {
        try {
            byte[] password = spec.encrypted()
                    ? spec.ownerPassword().getBytes(StandardCharsets.UTF_8)
                    : new byte[0];
            try (PdfReader reader = new PdfReader(Files.readAllBytes(source), password)) {
                return new OpenReadResult(true, reader.getNumberOfPages(), reader.isRebuilt(), null);
            }
        } catch (Exception error) {
            return new OpenReadResult(false, 0, false, describe(error));
        }
    }

    private void overlay(PdfStamper stamper, PdfReader reader, PhysicalPlacement placement)
            throws IOException, DocumentException {
        CoordinateTransforms.PageGeometry geometry = pageGeometry(reader, placement.pageNumber());
        BaseFont baseFont = BaseFont.createFont(
                fonts.get(placement.font()).toString(),
                BaseFont.IDENTITY_H,
                BaseFont.EMBEDDED);
        for (int codePoint : placement.text().codePoints().toArray()) {
            if (!baseFont.charExists(codePoint)) {
                throw new UnsupportedGlyphException(
                        "Font " + placement.font() + " lacks U+" + Integer.toHexString(codePoint).toUpperCase());
            }
        }
        PdfContentByte canvas = stamper.getOverContent(placement.pageNumber());
        // OpenPDF's FOP-backed Latin ligature substitution writes one Unicode
        // scalar to ToUnicode for a multi-character glyph. Keep exact text
        // semantics for ordinary overlays; RTL retains substitution for shaping.
        canvas.getPdfDocument().setGlyphSubstitutionEnabled(placement.rtl());
        drawCoordinateMarker(canvas, geometry, placement.xPt(), placement.baselineFromTopPt());
        CoordinateTransforms.TextMatrix matrix = CoordinateTransforms.uprightTextMatrix(
                geometry,
                placement.xPt(),
                placement.baselineFromTopPt());
        float fontSizeUser = (float) (placement.fontSizePt() / geometry.userUnit());
        if (placement.rtl() && geometry.rotation() == 0) {
            Font font = new Font(baseFont, fontSizeUser);
            ColumnText.showTextAligned(
                    canvas,
                    Element.ALIGN_LEFT,
                    new Phrase(placement.text(), font),
                    (float) matrix.e(),
                    (float) matrix.f(),
                    0,
                    PdfWriter.RUN_DIRECTION_RTL,
                    0);
        } else {
            canvas.saveState();
            canvas.setColorFill(new Color(17, 24, 39));
            canvas.beginText();
            canvas.setFontAndSize(baseFont, fontSizeUser);
            canvas.setTextMatrix(
                    (float) matrix.a(),
                    (float) matrix.b(),
                    (float) matrix.c(),
                    (float) matrix.d(),
                    (float) matrix.e(),
                    (float) matrix.f());
            canvas.showText(placement.text());
            canvas.endText();
            canvas.restoreState();
        }
    }

    private static void drawCoordinateMarker(
            PdfContentByte canvas,
            CoordinateTransforms.PageGeometry geometry,
            double xPt,
            double yPt) {
        double radius = 2.5;
        CoordinateTransforms.PdfPoint[] points = {
                CoordinateTransforms.physicalToPdf(geometry, xPt - radius, yPt - radius),
                CoordinateTransforms.physicalToPdf(geometry, xPt + radius, yPt - radius),
                CoordinateTransforms.physicalToPdf(geometry, xPt + radius, yPt + radius),
                CoordinateTransforms.physicalToPdf(geometry, xPt - radius, yPt + radius)
        };
        canvas.saveState();
        canvas.setRGBColorFill(255, 0, 255);
        canvas.moveTo((float) points[0].x(), (float) points[0].y());
        for (int index = 1; index < points.length; index++) {
            canvas.lineTo((float) points[index].x(), (float) points[index].y());
        }
        canvas.closePath();
        canvas.fill();
        canvas.restoreState();
    }

    private byte[] createContinuationPdf() throws DocumentException, IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        Document document = new Document(PageSize.LETTER, 54, 54, 64, 54);
        document.setGlyphSubstitutionEnabled(false);
        PdfWriter writer = PdfWriter.getInstance(document, output);
        BaseFont regular = BaseFont.createFont(
                fonts.get(FontKind.NOTO_SANS).toString(),
                BaseFont.IDENTITY_H,
                BaseFont.EMBEDDED);
        BaseFont bold = BaseFont.createFont(
                fonts.get(FontKind.NOTO_SANS).toString(),
                BaseFont.IDENTITY_H,
                BaseFont.EMBEDDED);
        writer.setPageEvent(new ContinuationPageEvent(regular));
        document.addTitle("Claros synthetic continuation pages");
        document.addCreator("OpenPDF 3.x hostile-PDF harness");
        document.open();

        Font eyebrowFont = new Font(bold, 10, Font.BOLD, new Color(29, 78, 216));
        Font headingFont = new Font(bold, 16, Font.BOLD, new Color(17, 24, 39));
        Font labelFont = new Font(bold, 10, Font.BOLD, new Color(51, 65, 85));
        Font bodyFont = new Font(regular, 11, Font.NORMAL, new Color(17, 24, 39));

        Paragraph eyebrow = new Paragraph("CLAROS ATTACHED ANSWER PAGE", eyebrowFont);
        eyebrow.setSpacingAfter(8);
        document.add(eyebrow);
        Paragraph worksheet = new Paragraph("Worksheet: " + CONTINUATION_WORKSHEET_TITLE, labelFont);
        worksheet.setSpacingAfter(3);
        document.add(worksheet);
        Paragraph sourcePage = new Paragraph(CONTINUATION_SOURCE_PAGE, labelFont);
        sourcePage.setSpacingAfter(12);
        document.add(sourcePage);
        Paragraph identifier = new Paragraph("Question " + CONTINUATION_QUESTION_ID, headingFont);
        identifier.setSpacingAfter(14);
        document.add(identifier);
        Paragraph questionLabel = new Paragraph("Exact source question", labelFont);
        questionLabel.setSpacingAfter(4);
        document.add(questionLabel);
        Paragraph question = new Paragraph(CONTINUATION_QUESTION, bodyFont);
        question.setLeading(15);
        question.setSpacingAfter(18);
        document.add(question);
        Paragraph answerLabel = new Paragraph("Exact approved answer", labelFont);
        answerLabel.setSpacingAfter(6);
        document.add(answerLabel);
        for (String paragraphText : CONTINUATION_ANSWER.split("\\n\\n", -1)) {
            Paragraph paragraph = new Paragraph(paragraphText, bodyFont);
            paragraph.setLeading(15);
            paragraph.setSpacingAfter(12);
            document.add(paragraph);
        }
        document.close();
        return output.toByteArray();
    }

    private static void appendContinuation(
            PdfStamper stamper,
            int sourcePageCount,
            PdfReader continuationReader) {
        for (int page = 1; page <= continuationReader.getNumberOfPages(); page++) {
            Rectangle sourceSize = continuationReader.getPageSize(page);
            Rectangle insertedSize = new Rectangle(sourceSize);
            insertedSize.setRotation(continuationReader.getPageRotation(page));
            int outputPage = sourcePageCount + page;
            stamper.insertPage(outputPage, insertedSize);
            PdfImportedPage imported = stamper.getImportedPage(continuationReader, page);
            stamper.getOverContent(outputPage).addTemplate(imported, 0, 0);
        }
    }

    private static List<PhysicalPlacement> createPlacements(FixtureSpec spec, PdfReader reader) {
        CoordinateTransforms.PageGeometry geometry = pageGeometry(reader, spec.overlayPage());
        double width = geometry.displayedWidthPt();
        double height = geometry.displayedHeightPt();
        List<PhysicalPlacement> placements = new ArrayList<>();
        int index = 0;
        for (Anchor anchor : spec.anchors()) {
            double x;
            double y;
            switch (anchor) {
                case UPPER_LEFT -> {
                    x = 18;
                    y = 22;
                }
                case UPPER_RIGHT -> {
                    x = Math.max(18, width - 190);
                    y = 22;
                }
                case CENTER -> {
                    x = Math.max(18, width / 2 - 100);
                    y = height / 2;
                }
                case LOWER_LEFT -> {
                    x = 18;
                    y = height - 10;
                }
                case LOWER_RIGHT -> {
                    x = Math.max(18, width - 190);
                    y = height - 10;
                }
                case CROP_TOP_LEFT -> {
                    x = 2;
                    y = 14;
                }
                case CROP_BOTTOM_RIGHT -> {
                    x = Math.max(2, width - 190);
                    y = height - 6;
                }
                default -> throw new IllegalStateException("Unknown anchor");
            }
            String text = spec.anchors().size() == 1
                    ? spec.overlayText()
                    : spec.overlayText() + " [" + anchor.name() + "]";
            placements.add(new PhysicalPlacement(
                    spec.id() + "-" + (++index),
                    spec.overlayPage(),
                    x,
                    y,
                    11,
                    Math.min(360, Math.max(100, width - x + 6)),
                    24,
                    text,
                    spec.overlayFont(),
                    spec.id().endsWith("-rtl")));
        }
        return List.copyOf(placements);
    }

    private static CoordinateTransforms.PageGeometry pageGeometry(PdfReader reader, int pageNumber) {
        Rectangle crop = reader.getCropBox(pageNumber);
        PdfNumber userUnitNumber = reader.getPageN(pageNumber).getAsNumber(PdfName.USERUNIT);
        double userUnit = userUnitNumber == null ? 1 : userUnitNumber.doubleValue();
        return new CoordinateTransforms.PageGeometry(
                crop.getLeft(),
                crop.getBottom(),
                crop.getWidth(),
                crop.getHeight(),
                reader.getPageRotation(pageNumber),
                userUnit);
    }

    private static String buildLongAnswer() {
        String paragraphOne = "The approved answer must remain exact, readable, and connected to its stable question "
                + "identifier. It includes punctuation (parentheses), a backslash \\, accents such as é, ñ, and ü, "
                + "and the symbols α, β, and Γ. ";
        String paragraphTwo = "A continuation page must wrap this wording without truncating it or silently moving "
                + "the source worksheet. Every source page remains immutable while only derivative pages are added. ";
        String paragraphThree = "Page numbering is visible on every attached page, and this deliberately repeated "
                + "evidence makes the answer span more than one page under ordinary eleven-point layout. ";
        return (paragraphOne.repeat(14) + "\n\n"
                + paragraphTwo.repeat(14) + "\n\n"
                + paragraphThree.repeat(14)).strip();
    }

    private static String describe(Throwable error) {
        String message = error.getMessage();
        return error.getClass().getSimpleName() + (message == null ? "" : ": " + message);
    }

    public record OpenResult(
            Path derivative,
            List<PhysicalPlacement> placements,
            int continuationPages,
            boolean readerRebuilt,
            boolean incrementalAppend,
            String derivativeSha256) {
    }

    public record OpenReadResult(boolean opened, int pageCount, boolean readerRebuilt, String error) {
    }

    public static final class UnsupportedGlyphException extends DocumentException {
        public UnsupportedGlyphException(String message) {
            super(message);
        }
    }

    private static final class ContinuationPageEvent extends PdfPageEventHelper {
        private final BaseFont font;

        private ContinuationPageEvent(BaseFont font) {
            this.font = font;
        }

        @Override
        public void onEndPage(PdfWriter writer, Document document) {
            PdfContentByte canvas = writer.getDirectContent();
            canvas.saveState();
            canvas.setColorFill(new Color(71, 85, 105));
            canvas.beginText();
            canvas.setFontAndSize(font, 9);
            canvas.showTextAligned(
                    PdfContentByte.ALIGN_RIGHT,
                    "Attached answer page " + writer.getPageNumber(),
                    document.right(),
                    32,
                    0);
            canvas.endText();
            canvas.restoreState();
        }
    }
}
