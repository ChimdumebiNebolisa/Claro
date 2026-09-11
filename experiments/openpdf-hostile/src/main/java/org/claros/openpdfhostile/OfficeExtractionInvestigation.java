package org.claros.openpdfhostile;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.cos.COSArray;
import org.apache.pdfbox.cos.COSBase;
import org.apache.pdfbox.cos.COSDictionary;
import org.apache.pdfbox.cos.COSName;
import org.apache.pdfbox.cos.COSStream;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDDocumentInformation;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.PDPageContentStream;
import org.apache.pdfbox.pdmodel.PDResources;
import org.apache.pdfbox.pdmodel.common.PDRectangle;
import org.apache.pdfbox.pdmodel.common.PDStream;
import org.apache.pdfbox.pdmodel.font.PDFont;
import org.apache.pdfbox.pdmodel.font.PDFontDescriptor;
import org.apache.pdfbox.pdmodel.font.PDType1Font;
import org.apache.pdfbox.pdmodel.font.Standard14Fonts;
import org.apache.pdfbox.text.PDFTextStripper;
import org.openpdf.text.pdf.BaseFont;
import org.openpdf.text.pdf.PdfContentByte;
import org.openpdf.text.pdf.PdfReader;
import org.openpdf.text.pdf.PdfStamper;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class OfficeExtractionInvestigation {
    public static final List<String> WORDS = List.of(
            "office", "official", "efficient", "file", "first", "affinity", "different");

    private static final ObjectMapper JSON = new ObjectMapper()
            .enable(SerializationFeature.INDENT_OUTPUT);

    private OfficeExtractionInvestigation() {
    }

    public static InvestigationResult run(Path experimentRoot, Path targetRoot) throws Exception {
        Path outputRoot = targetRoot.resolve("office-investigation");
        Files.createDirectories(outputRoot);
        Map<FontKind, Path> fonts = FontAssets.prepare(experimentRoot, targetRoot);
        Path officeSource = targetRoot.resolve("fixtures/office-style.pdf");
        if (!Files.isRegularFile(officeSource)) {
            new CorpusGenerator(targetRoot.resolve("fixtures"), fonts).generateAll();
        }

        Path caseB = outputRoot.resolve("B-open-write.pdf");
        Path caseC = outputRoot.resolve("C-unrelated-overlay.pdf");
        Path caseD = outputRoot.resolve("D-office-overlay.pdf");
        stamp(officeSource, caseB, null, fonts.get(FontKind.NOTO_SANS),
                BaseFont.IDENTITY_H, true, true, true);
        stamp(officeSource, caseC, List.of("CLAROS marker"), fonts.get(FontKind.NOTO_SANS),
                BaseFont.IDENTITY_H, true, true, true);
        stamp(officeSource, caseD, List.of("CLAROS office overlay"), fonts.get(FontKind.NOTO_SANS),
                BaseFont.IDENTITY_H, true, true, true);

        Path minimalSource = outputRoot.resolve("minimal-source.pdf");
        createMinimalSource(minimalSource);
        Map<String, Path> cases = new LinkedHashMap<>();
        cases.put("A-original-untouched", officeSource);
        cases.put("B-open-write-no-content", caseB);
        cases.put("C-unrelated-overlay", caseC);
        cases.put("D-office-overlay", caseD);
        cases.put("minimal-source", minimalSource);

        cases.put("minimal-default-fop", stampMinimal(
                minimalSource, outputRoot.resolve("minimal-default-fop.pdf"), fonts.get(FontKind.NOTO_SANS),
                BaseFont.IDENTITY_H, true, true, true));
        cases.put("minimal-no-subset", stampMinimal(
                minimalSource, outputRoot.resolve("minimal-no-subset.pdf"), fonts.get(FontKind.NOTO_SANS),
                BaseFont.IDENTITY_H, true, false, true));
        cases.put("minimal-no-glyph-substitution", stampMinimal(
                minimalSource, outputRoot.resolve("minimal-no-glyph-substitution.pdf"),
                fonts.get(FontKind.NOTO_SANS), BaseFont.IDENTITY_H, true, true, false));
        cases.put("minimal-math-font", stampMinimal(
                minimalSource, outputRoot.resolve("minimal-math-font.pdf"), fonts.get(FontKind.NOTO_MATH),
                BaseFont.IDENTITY_H, true, true, true));
        cases.put("minimal-winansi", stampMinimal(
                minimalSource, outputRoot.resolve("minimal-winansi.pdf"), fonts.get(FontKind.NOTO_SANS),
                BaseFont.CP1252, true, true, true));
        cases.put("minimal-full-rewrite", stampMinimal(
                minimalSource, outputRoot.resolve("minimal-full-rewrite.pdf"), fonts.get(FontKind.NOTO_SANS),
                BaseFont.IDENTITY_H, true, true, true, false));

        List<CaseEvidence> evidence = new ArrayList<>();
        for (Map.Entry<String, Path> item : cases.entrySet()) {
            evidence.add(inspect(item.getKey(), experimentRoot, item.getValue()));
        }
        InvestigationResult result = new InvestigationResult(
                "claros-office-extraction-investigation-v1",
                List.copyOf(WORDS),
                List.copyOf(evidence));
        JSON.writeValue(outputRoot.resolve("pdfbox-structure-results.json").toFile(), result);
        JSON.writeValue(outputRoot.resolve("pdfjs-inputs.json").toFile(), evidence.stream()
                .map(item -> Map.of("id", item.id(), "path", item.absolutePath()))
                .toList());
        return result;
    }

    static Path stampMinimal(
            Path source,
            Path output,
            Path font,
            String encoding,
            boolean embedded,
            boolean subset,
            boolean glyphSubstitution) throws Exception {
        return stampMinimal(source, output, font, encoding, embedded, subset, glyphSubstitution, true);
    }

    private static Path stampMinimal(
            Path source,
            Path output,
            Path font,
            String encoding,
            boolean embedded,
            boolean subset,
            boolean glyphSubstitution,
            boolean incremental) throws Exception {
        stamp(source, output, WORDS, font, encoding, embedded, subset, glyphSubstitution, incremental);
        return output;
    }

    static void stamp(
            Path source,
            Path output,
            List<String> overlayLines,
            Path font,
            String encoding,
            boolean embedded,
            boolean subset,
            boolean glyphSubstitution) throws Exception {
        stamp(source, output, overlayLines, font, encoding, embedded, subset, glyphSubstitution, true);
    }

    private static void stamp(
            Path source,
            Path output,
            List<String> overlayLines,
            Path font,
            String encoding,
            boolean embedded,
            boolean subset,
            boolean glyphSubstitution,
            boolean incremental) throws Exception {
        byte[] sourceBytes = Files.readAllBytes(source);
        ByteArrayOutputStream outputBytes = new ByteArrayOutputStream();
        try (PdfReader reader = new PdfReader(sourceBytes);
             PdfStamper stamper = new PdfStamper(reader, outputBytes, null, incremental)) {
            stamper.setRotateContents(false);
            stamper.setUpdateDocInfo(false);
            stamper.setUpdateMetadata(false);
            if (overlayLines != null) {
                PdfContentByte canvas = stamper.getOverContent(1);
                canvas.getPdfDocument().setGlyphSubstitutionEnabled(glyphSubstitution);
                BaseFont baseFont = BaseFont.createFont(
                        font.toString(), encoding, embedded ? BaseFont.EMBEDDED : BaseFont.NOT_EMBEDDED);
                baseFont.setSubset(subset);
                float y = 650;
                for (String line : overlayLines) {
                    canvas.beginText();
                    canvas.setFontAndSize(baseFont, 14);
                    canvas.setTextMatrix(72, y);
                    canvas.showText(line);
                    canvas.endText();
                    y -= 28;
                }
            }
        }
        Files.write(output, outputBytes.toByteArray());
    }

    static void createMinimalSource(Path output) throws IOException {
        createMinimalSource(output, "minimal source");
    }

    static void createMinimalSource(Path output, String sourceText) throws IOException {
        Files.createDirectories(output.getParent());
        Files.deleteIfExists(output);
        try (PDDocument document = new PDDocument()) {
            PDDocumentInformation info = new PDDocumentInformation();
            info.setTitle("Minimal OpenPDF ligature reproduction");
            info.setCreator("Apache PDFBox independent fixture generator");
            info.setProducer("Apache PDFBox independent fixture generator");
            document.setDocumentInformation(info);
            PDPage page = new PDPage(PDRectangle.LETTER);
            document.addPage(page);
            try (PDPageContentStream content = new PDPageContentStream(document, page)) {
                content.beginText();
                content.setFont(new PDType1Font(Standard14Fonts.FontName.HELVETICA), 10);
                content.newLineAtOffset(72, 720);
                content.showText(sourceText);
                content.endText();
            }
            document.save(output.toFile());
        }
    }

    static CaseEvidence inspect(String id, Path experimentRoot, Path pdf) throws IOException {
        try (PDDocument document = Loader.loadPDF(pdf.toFile())) {
            PDFTextStripper stripper = new PDFTextStripper();
            stripper.setSortByPosition(false);
            String text = normalize(stripper.getText(document)).stripTrailing();
            PDPage page = document.getPage(0);
            List<StreamEvidence> streams = new ArrayList<>();
            Iterator<PDStream> contentStreams = page.getContentStreams();
            while (contentStreams.hasNext()) {
                try (InputStream input = contentStreams.next().createInputStream()) {
                    byte[] bytes = input.readAllBytes();
                    streams.add(new StreamEvidence(sha256(bytes), HexFormat.of().formatHex(bytes)));
                }
            }
            List<FontEvidence> fontEvidence = new ArrayList<>();
            PDResources resources = page.getResources();
            for (COSName name : resources.getFontNames()) {
                PDFont pdfFont = resources.getFont(name);
                COSDictionary dictionary = pdfFont.getCOSObject();
                COSBase encoding = dictionary.getDictionaryObject(COSName.ENCODING);
                COSBase toUnicode = dictionary.getDictionaryObject(COSName.TO_UNICODE);
                String toUnicodeText = "";
                String toUnicodeSha256 = "";
                if (toUnicode instanceof COSStream stream) {
                    try (InputStream input = stream.createInputStream()) {
                        byte[] bytes = input.readAllBytes();
                        toUnicodeText = new String(bytes, StandardCharsets.ISO_8859_1);
                        toUnicodeSha256 = sha256(bytes);
                    }
                }
                String descendantSubtype = "";
                String cidToGidMap = "";
                COSArray descendants = dictionary.getCOSArray(COSName.DESCENDANT_FONTS);
                if (descendants != null && descendants.size() > 0
                        && descendants.getObject(0) instanceof COSDictionary descendant) {
                    descendantSubtype = descendant.getNameAsString(COSName.SUBTYPE, "");
                    COSBase map = descendant.getDictionaryObject(COSName.CID_TO_GID_MAP);
                    cidToGidMap = map == null ? "" : map.toString();
                }
                PDFontDescriptor descriptor = pdfFont.getFontDescriptor();
                String embeddedSha256 = "";
                if (descriptor != null) {
                    PDStream embedded = descriptor.getFontFile2();
                    if (embedded == null) {
                        embedded = descriptor.getFontFile3();
                    }
                    if (embedded == null) {
                        embedded = descriptor.getFontFile();
                    }
                    if (embedded != null) {
                        try (InputStream input = embedded.createInputStream()) {
                            embeddedSha256 = sha256(input.readAllBytes());
                        }
                    }
                }
                fontEvidence.add(new FontEvidence(
                        name.getName(),
                        dictionary.getNameAsString(COSName.SUBTYPE, ""),
                        dictionary.getNameAsString(COSName.BASE_FONT, ""),
                        encoding == null ? "" : encoding.toString(),
                        descendantSubtype,
                        cidToGidMap,
                        toUnicodeSha256,
                        toUnicodeText,
                        embeddedSha256));
            }
            return new CaseEvidence(
                    id,
                    experimentRoot.relativize(pdf.toAbsolutePath().normalize()).toString().replace('\\', '/'),
                    pdf.toAbsolutePath().normalize().toString(),
                    FontAssets.digest(pdf),
                    text,
                    List.copyOf(streams),
                    List.copyOf(fontEvidence));
        }
    }

    private static String normalize(String value) {
        return value.replace("\r\n", "\n").replace('\r', '\n');
    }

    private static String sha256(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException(error);
        }
    }

    public record InvestigationResult(
            String schemaVersion,
            List<String> testWords,
            List<CaseEvidence> cases) {
    }

    public record CaseEvidence(
            String id,
            String relativePath,
            String absolutePath,
            String sha256,
            String pdfBoxText,
            List<StreamEvidence> contentStreams,
            List<FontEvidence> fonts) {
    }

    public record StreamEvidence(String decodedSha256, String decodedHex) {
    }

    public record FontEvidence(
            String resourceName,
            String subtype,
            String baseFont,
            String encoding,
            String descendantSubtype,
            String cidToGidMap,
            String toUnicodeSha256,
            String toUnicode,
            String embeddedFontSha256) {
    }
}
