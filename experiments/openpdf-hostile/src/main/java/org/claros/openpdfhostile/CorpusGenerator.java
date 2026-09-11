package org.claros.openpdfhostile;

import org.apache.pdfbox.cos.COSName;
import org.apache.pdfbox.pdfwriter.compress.CompressParameters;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDDocumentInformation;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.PDPageContentStream;
import org.apache.pdfbox.pdmodel.PDPageContentStream.AppendMode;
import org.apache.pdfbox.pdmodel.PDResources;
import org.apache.pdfbox.pdmodel.common.PDMetadata;
import org.apache.pdfbox.pdmodel.common.PDRectangle;
import org.apache.pdfbox.pdmodel.encryption.AccessPermission;
import org.apache.pdfbox.pdmodel.encryption.StandardProtectionPolicy;
import org.apache.pdfbox.pdmodel.font.PDFont;
import org.apache.pdfbox.pdmodel.font.PDType0Font;
import org.apache.pdfbox.pdmodel.font.PDType1Font;
import org.apache.pdfbox.pdmodel.font.Standard14Fonts;
import org.apache.pdfbox.pdmodel.graphics.image.LosslessFactory;
import org.apache.pdfbox.pdmodel.graphics.image.PDImageXObject;
import org.apache.pdfbox.pdmodel.graphics.state.PDExtendedGraphicsState;
import org.apache.pdfbox.pdmodel.interactive.action.PDActionURI;
import org.apache.pdfbox.pdmodel.interactive.annotation.PDAnnotationLink;
import org.apache.pdfbox.pdmodel.interactive.annotation.PDAnnotationText;
import org.apache.pdfbox.pdmodel.interactive.annotation.PDAnnotationWidget;
import org.apache.pdfbox.pdmodel.interactive.annotation.PDBorderStyleDictionary;
import org.apache.pdfbox.pdmodel.interactive.documentnavigation.destination.PDPageFitDestination;
import org.apache.pdfbox.pdmodel.interactive.documentnavigation.outline.PDDocumentOutline;
import org.apache.pdfbox.pdmodel.interactive.documentnavigation.outline.PDOutlineItem;
import org.apache.pdfbox.pdmodel.interactive.form.PDAcroForm;
import org.apache.pdfbox.pdmodel.interactive.form.PDTextField;

import java.awt.Color;
import java.awt.Font;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.GregorianCalendar;
import java.util.List;
import java.util.Map;
import java.util.TimeZone;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class CorpusGenerator {
    private static final PDType1Font HELVETICA = new PDType1Font(Standard14Fonts.FontName.HELVETICA);
    private static final PDType1Font HELVETICA_BOLD =
            new PDType1Font(Standard14Fonts.FontName.HELVETICA_BOLD);
    private static final Pattern START_XREF = Pattern.compile("startxref\\s+(\\d+)", Pattern.MULTILINE);

    private final Path fixtureDirectory;
    private final Map<FontKind, Path> fonts;

    public CorpusGenerator(Path fixtureDirectory, Map<FontKind, Path> fonts) {
        this.fixtureDirectory = fixtureDirectory;
        this.fonts = fonts;
    }

    public List<GeneratedFixture> generateAll() throws IOException {
        Files.createDirectories(fixtureDirectory);
        List<GeneratedFixture> generated = new ArrayList<>();
        for (FixtureSpec spec : CorpusPlan.fixtures()) {
            Path path = fixtureDirectory.resolve(spec.id() + ".pdf");
            generate(spec, path);
            generated.add(new GeneratedFixture(
                    spec,
                    path,
                    FontAssets.digest(path),
                    Files.size(path)));
        }
        return List.copyOf(generated);
    }

    private void generate(FixtureSpec spec, Path output) throws IOException {
        Files.deleteIfExists(output);
        try (PDDocument document = new PDDocument()) {
            configureDeterministicMetadata(document, spec);
            switch (spec.id()) {
                case "mixed-page-sizes" -> generateMixedSizes(document, spec);
                case "rotated-90" -> addBasicPage(document, spec, PDRectangle.LETTER, 90);
                case "rotated-180" -> addBasicPage(document, spec, PDRectangle.LETTER, 180);
                case "rotated-270" -> addBasicPage(document, spec, PDRectangle.LETTER, 270);
                case "cropbox-offset" -> generateCropBox(document, spec);
                case "trim-bleed-boxes" -> generatePageBoxes(document, spec);
                case "mixed-rotations" -> generateMixedRotations(document, spec);
                case "annotations" -> generateAnnotation(document, spec);
                case "acroform" -> generateAcroForm(document, spec);
                case "existing-images" -> generateImagePage(document, spec, false);
                case "vector-graphics" -> generateVectorPage(document, spec);
                case "transparency" -> generateTransparencyPage(document, spec);
                case "object-stream-heavy" -> generateCompressed(document, spec);
                case "office-style" -> generateOfficeStyle(document, spec);
                case "scanned-image-only" -> generateImagePage(document, spec, true);
                case "large-multipage" -> generateLarge(document, spec);
                case "outlines" -> generateOutlines(document, spec);
                case "links" -> generateLink(document, spec);
                case "metadata" -> generateMetadata(document, spec);
                case "user-unit-2" -> generateUserUnit(document, spec);
                default -> addBasicPage(
                        document,
                        spec,
                        spec.id().equals("a4") ? PDRectangle.A4 : PDRectangle.LETTER,
                        0);
            }
            if (spec.encrypted()) {
                AccessPermission permissions = new AccessPermission();
                permissions.setCanPrint(false);
                permissions.setCanModify(false);
                permissions.setCanExtractContent(true);
                StandardProtectionPolicy policy = new StandardProtectionPolicy(
                        spec.ownerPassword(),
                        spec.userPassword(),
                        permissions);
                policy.setEncryptionKeyLength(128);
                policy.setPreferAES(true);
                document.protect(policy);
            }
            CompressParameters compression = spec.id().equals("object-stream-heavy")
                    ? CompressParameters.DEFAULT_COMPRESSION
                    : CompressParameters.NO_COMPRESSION;
            document.save(output.toFile(), compression);
        }
        if (spec.malformed()) {
            corruptStartXrefDeterministically(output);
        }
    }

    private void addBasicPage(PDDocument document, FixtureSpec spec, PDRectangle size, int rotation)
            throws IOException {
        PDPage page = new PDPage(size);
        page.setRotation(rotation);
        document.addPage(page);
        drawBasePage(document, page, spec, 1);
    }

    private void drawBasePage(PDDocument document, PDPage page, FixtureSpec spec, int pageNumber)
            throws IOException {
        try (PDPageContentStream content = new PDPageContentStream(document, page, AppendMode.APPEND, true)) {
            float width = page.getMediaBox().getWidth();
            float height = page.getMediaBox().getHeight();
            content.setNonStrokingColor(new Color(248, 250, 252));
            content.addRect(0, 0, width, height);
            content.fill();
            content.setNonStrokingColor(new Color(29, 78, 216));
            content.addRect(36, height - 74, Math.max(120, width - 72), 34);
            content.fill();
            drawText(content, HELVETICA_BOLD, 15, 48, height - 62,
                    "CLAROS SYNTHETIC HOSTILE FIXTURE");
            PDFont sourceFont = sourceFont(document, spec);
            drawText(content, sourceFont, 12, 48, height - 112,
                    spec.sourceText().isBlank() ? " " : spec.sourceText());
            drawText(content, HELVETICA, 9, 48, 34,
                    "Project-authored synthetic PDF - page " + pageNumber);
            content.setStrokingColor(new Color(100, 116, 139));
            content.setLineWidth(0.75f);
            content.addRect(42, 70, Math.max(60, width - 84), Math.max(80, height - 220));
            content.stroke();
        }
    }

    private PDFont sourceFont(PDDocument document, FixtureSpec spec) throws IOException {
        if (!spec.unicodeCase() && !spec.id().equals("embedded-font")) {
            return HELVETICA;
        }
        try (InputStream input = Files.newInputStream(fonts.get(spec.overlayFont()))) {
            return PDType0Font.load(document, input, true);
        }
    }

    private void generateMixedSizes(PDDocument document, FixtureSpec spec) throws IOException {
        PDRectangle[] sizes = {PDRectangle.LETTER, PDRectangle.A4, PDRectangle.LEGAL};
        for (int index = 0; index < sizes.length; index++) {
            PDPage page = new PDPage(sizes[index]);
            document.addPage(page);
            drawBasePage(document, page, spec, index + 1);
        }
    }

    private void generateCropBox(PDDocument document, FixtureSpec spec) throws IOException {
        PDPage page = new PDPage(PDRectangle.LETTER);
        page.setCropBox(new PDRectangle(36, 54, 540, 684));
        document.addPage(page);
        drawBasePage(document, page, spec, 1);
    }

    private void generatePageBoxes(PDDocument document, FixtureSpec spec) throws IOException {
        PDPage page = new PDPage(PDRectangle.LETTER);
        page.setCropBox(new PDRectangle(18, 18, 576, 756));
        page.setBleedBox(new PDRectangle(24, 24, 564, 744));
        page.setTrimBox(new PDRectangle(30, 30, 552, 732));
        page.setArtBox(new PDRectangle(36, 36, 540, 720));
        document.addPage(page);
        drawBasePage(document, page, spec, 1);
    }

    private void generateMixedRotations(PDDocument document, FixtureSpec spec) throws IOException {
        int[] rotations = {0, 90, 180, 270};
        for (int index = 0; index < rotations.length; index++) {
            PDPage page = new PDPage(PDRectangle.LETTER);
            page.setRotation(rotations[index]);
            document.addPage(page);
            drawBasePage(document, page, spec, index + 1);
        }
    }

    private void generateAnnotation(PDDocument document, FixtureSpec spec) throws IOException {
        addBasicPage(document, spec, PDRectangle.LETTER, 0);
        PDAnnotationText annotation = new PDAnnotationText();
        annotation.setContents("Synthetic reviewer note - preserve exactly");
        annotation.setName(PDAnnotationText.NAME_COMMENT);
        annotation.setRectangle(new PDRectangle(72, 620, 28, 28));
        annotation.setOpen(false);
        document.getPage(0).getAnnotations().add(annotation);
    }

    private void generateAcroForm(PDDocument document, FixtureSpec spec) throws IOException {
        addBasicPage(document, spec, PDRectangle.LETTER, 0);
        PDAcroForm form = new PDAcroForm(document);
        document.getDocumentCatalog().setAcroForm(form);
        PDResources resources = new PDResources();
        COSName fontName = resources.add(HELVETICA);
        form.setDefaultResources(resources);
        form.setDefaultAppearance("/" + fontName.getName() + " 11 Tf 0 g");
        form.setNeedAppearances(false);

        PDTextField field = new PDTextField(form);
        field.setPartialName("student_name");
        field.setAlternateFieldName("Student name");
        PDAnnotationWidget widget = field.getWidgets().getFirst();
        widget.setRectangle(new PDRectangle(72, 590, 220, 28));
        widget.setPage(document.getPage(0));
        document.getPage(0).getAnnotations().add(widget);
        form.getFields().add(field);
        field.setValue("Ada Student");
        form.refreshAppearances();
    }

    private void generateImagePage(PDDocument document, FixtureSpec spec, boolean scanOnly)
            throws IOException {
        PDPage page = new PDPage(PDRectangle.LETTER);
        document.addPage(page);
        if (!scanOnly) {
            drawBasePage(document, page, spec, 1);
        }
        BufferedImage image = new BufferedImage(scanOnly ? 1224 : 480, scanOnly ? 1584 : 260,
                BufferedImage.TYPE_INT_RGB);
        Graphics2D graphics = image.createGraphics();
        graphics.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
        graphics.setColor(Color.WHITE);
        graphics.fillRect(0, 0, image.getWidth(), image.getHeight());
        graphics.setColor(new Color(30, 64, 175));
        graphics.fillRoundRect(24, 24, image.getWidth() - 48, 80, 18, 18);
        graphics.setColor(Color.BLACK);
        graphics.setFont(new Font(Font.SANS_SERIF, Font.BOLD, scanOnly ? 42 : 24));
        graphics.drawString(scanOnly ? "SCANNED SYNTHETIC WORKSHEET" : "Synthetic raster image",
                48, scanOnly ? 190 : 165);
        graphics.setFont(new Font(Font.SANS_SERIF, Font.PLAIN, scanOnly ? 30 : 18));
        graphics.drawString("No private or copyrighted worksheet content", 48,
                scanOnly ? 250 : 205);
        graphics.dispose();
        PDImageXObject xObject = LosslessFactory.createFromImage(document, image);
        try (PDPageContentStream content = new PDPageContentStream(document, page, AppendMode.APPEND, true)) {
            if (scanOnly) {
                content.drawImage(xObject, 0, 0, PDRectangle.LETTER.getWidth(), PDRectangle.LETTER.getHeight());
            } else {
                content.drawImage(xObject, 90, 240, 432, 234);
            }
        }
    }

    private void generateVectorPage(PDDocument document, FixtureSpec spec) throws IOException {
        addBasicPage(document, spec, PDRectangle.LETTER, 0);
        try (PDPageContentStream content = new PDPageContentStream(
                document, document.getPage(0), AppendMode.APPEND, true, true)) {
            content.setStrokingColor(new Color(22, 101, 52));
            content.setLineWidth(3);
            content.moveTo(120, 250);
            content.curveTo(180, 430, 360, 80, 490, 320);
            content.stroke();
            content.setNonStrokingColor(new Color(254, 215, 170));
            content.addRect(150, 340, 250, 100);
            content.fill();
        }
    }

    private void generateTransparencyPage(PDDocument document, FixtureSpec spec) throws IOException {
        addBasicPage(document, spec, PDRectangle.LETTER, 0);
        try (PDPageContentStream content = new PDPageContentStream(
                document, document.getPage(0), AppendMode.APPEND, true, true)) {
            PDExtendedGraphicsState alpha = new PDExtendedGraphicsState();
            alpha.setNonStrokingAlphaConstant(0.45f);
            content.setGraphicsStateParameters(alpha);
            content.setNonStrokingColor(Color.RED);
            content.addRect(150, 270, 190, 190);
            content.fill();
            content.setNonStrokingColor(Color.BLUE);
            content.addRect(260, 210, 190, 190);
            content.fill();
        }
    }

    private void generateCompressed(PDDocument document, FixtureSpec spec) throws IOException {
        for (int index = 0; index < 24; index++) {
            PDPage page = new PDPage(index % 2 == 0 ? PDRectangle.LETTER : PDRectangle.A4);
            document.addPage(page);
            drawBasePage(document, page, spec, index + 1);
            try (PDPageContentStream content = new PDPageContentStream(
                    document, page, AppendMode.APPEND, true, true)) {
                for (int shape = 0; shape < 20; shape++) {
                    content.setNonStrokingColor(new Color(
                            (index * 17 + shape * 11) % 255,
                            (index * 29 + shape * 7) % 255,
                            (index * 13 + shape * 19) % 255));
                    content.addRect(60 + shape * 8, 160 + (shape % 5) * 24, 40, 16);
                    content.fill();
                }
            }
        }
    }

    private void generateOfficeStyle(PDDocument document, FixtureSpec spec) throws IOException {
        PDPage page = new PDPage(PDRectangle.LETTER);
        document.addPage(page);
        try (PDPageContentStream content = new PDPageContentStream(document, page)) {
            content.setNonStrokingColor(Color.WHITE);
            content.addRect(0, 0, 612, 792);
            content.fill();
            content.setNonStrokingColor(new Color(31, 78, 121));
            content.addRect(0, 720, 612, 72);
            content.fill();
            drawText(content, HELVETICA_BOLD, 22, 42, 748, "Synthetic quarterly study plan");
            drawText(content, HELVETICA, 11, 42, 680, "Prepared for OpenPDF preservation testing");
            content.setStrokingColor(new Color(148, 163, 184));
            float left = 42;
            float bottom = 300;
            float tableWidth = 528;
            float rowHeight = 42;
            for (int row = 0; row <= 7; row++) {
                content.moveTo(left, bottom + row * rowHeight);
                content.lineTo(left + tableWidth, bottom + row * rowHeight);
            }
            for (int column = 0; column <= 3; column++) {
                float x = left + column * tableWidth / 3;
                content.moveTo(x, bottom);
                content.lineTo(x, bottom + 7 * rowHeight);
            }
            content.stroke();
            for (int row = 0; row < 6; row++) {
                drawText(content, HELVETICA, 10, left + 10, bottom + 20 + row * rowHeight,
                        "Office-style row " + (row + 1));
            }
            drawText(content, HELVETICA, 8, 42, 30, "Synthetic equivalent - not exported by an office suite");
        }
    }

    private void generateLarge(PDDocument document, FixtureSpec spec) throws IOException {
        for (int index = 0; index < 60; index++) {
            PDPage page = new PDPage(PDRectangle.LETTER);
            document.addPage(page);
            drawBasePage(document, page, spec, index + 1);
        }
    }

    private void generateOutlines(PDDocument document, FixtureSpec spec) throws IOException {
        for (int index = 0; index < 3; index++) {
            PDPage page = new PDPage(PDRectangle.LETTER);
            document.addPage(page);
            drawBasePage(document, page, spec, index + 1);
        }
        PDDocumentOutline outline = new PDDocumentOutline();
        document.getDocumentCatalog().setDocumentOutline(outline);
        for (int index = 0; index < 3; index++) {
            PDOutlineItem item = new PDOutlineItem();
            item.setTitle("Synthetic section " + (index + 1));
            PDPageFitDestination destination = new PDPageFitDestination();
            destination.setPage(document.getPage(index));
            item.setDestination(destination);
            outline.addLast(item);
        }
        outline.openNode();
    }

    private void generateLink(PDDocument document, FixtureSpec spec) throws IOException {
        addBasicPage(document, spec, PDRectangle.LETTER, 0);
        PDAnnotationLink link = new PDAnnotationLink();
        link.setRectangle(new PDRectangle(72, 575, 260, 24));
        PDBorderStyleDictionary border = new PDBorderStyleDictionary();
        border.setStyle(PDBorderStyleDictionary.STYLE_UNDERLINE);
        border.setWidth(1);
        link.setBorderStyle(border);
        PDActionURI action = new PDActionURI();
        action.setURI("https://example.invalid/claros-synthetic-link");
        link.setAction(action);
        document.getPage(0).getAnnotations().add(link);
    }

    private void generateMetadata(PDDocument document, FixtureSpec spec) throws IOException {
        addBasicPage(document, spec, PDRectangle.LETTER, 0);
        PDDocumentInformation info = document.getDocumentInformation();
        info.setTitle("Claros synthetic metadata fixture");
        info.setAuthor("Claros test harness");
        info.setSubject("Preservation of unrelated document metadata");
        info.setKeywords("synthetic,openpdf,preservation");
        info.setCustomMetadataValue("ClarosFixture", "metadata-v1");
        String xmp = """
                <?xpacket begin="\uFEFF" id="W5M0MpCehiHzreSzNTczkc9d"?>
                <x:xmpmeta xmlns:x="adobe:ns:meta/">
                  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
                    <rdf:Description rdf:about="" xmlns:claros="https://claros.invalid/ns/1.0/"
                      claros:fixture="metadata-v1"/>
                  </rdf:RDF>
                </x:xmpmeta>
                <?xpacket end="w"?>
                """;
        PDMetadata metadata = new PDMetadata(document);
        metadata.importXMPMetadata(xmp.getBytes(StandardCharsets.UTF_8));
        document.getDocumentCatalog().setMetadata(metadata);
    }

    private void generateUserUnit(PDDocument document, FixtureSpec spec) throws IOException {
        PDPage page = new PDPage(new PDRectangle(306, 396));
        page.setUserUnit(2f);
        document.addPage(page);
        drawBasePage(document, page, spec, 1);
    }

    private static void drawText(
            PDPageContentStream content,
            PDFont font,
            float size,
            float x,
            float y,
            String text) throws IOException {
        content.beginText();
        content.setFont(font, size);
        content.newLineAtOffset(x, y);
        content.showText(text);
        content.endText();
    }

    private static void configureDeterministicMetadata(PDDocument document, FixtureSpec spec) {
        PDDocumentInformation info = new PDDocumentInformation();
        info.setTitle("Claros hostile fixture: " + spec.id());
        info.setAuthor("Claros synthetic test harness");
        info.setCreator("Apache PDFBox fixture generator");
        info.setProducer("Apache PDFBox fixture generator");
        Calendar fixed = GregorianCalendar.from(Instant.parse("2026-01-01T00:00:00Z")
                .atZone(java.time.ZoneOffset.UTC));
        fixed.setTimeZone(TimeZone.getTimeZone("UTC"));
        info.setCreationDate(fixed);
        info.setModificationDate((Calendar) fixed.clone());
        document.setDocumentInformation(info);
        document.setDocumentId((long) spec.id().hashCode() & 0xffffffffL);
    }

    private static void corruptStartXrefDeterministically(Path path) throws IOException {
        byte[] bytes = Files.readAllBytes(path);
        String text = new String(bytes, StandardCharsets.ISO_8859_1);
        Matcher matcher = START_XREF.matcher(text);
        if (!matcher.find()) {
            throw new IOException("Generated PDF lacks startxref");
        }
        int original = Integer.parseInt(matcher.group(1));
        String replacement = String.format("%0" + matcher.group(1).length() + "d", original + 7);
        String malformed = text.substring(0, matcher.start(1))
                + replacement
                + text.substring(matcher.end(1));
        Files.write(path, malformed.getBytes(StandardCharsets.ISO_8859_1));
    }

    public record GeneratedFixture(FixtureSpec spec, Path path, String sha256, long sizeBytes) {
    }
}
