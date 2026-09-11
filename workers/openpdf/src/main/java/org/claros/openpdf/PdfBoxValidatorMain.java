package org.claros.openpdf;

import com.fasterxml.jackson.databind.node.ObjectNode;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.cos.COSArray;
import org.apache.pdfbox.cos.COSBase;
import org.apache.pdfbox.cos.COSName;
import org.apache.pdfbox.cos.COSStream;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDDocumentInformation;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.PDResources;
import org.apache.pdfbox.pdmodel.common.PDMetadata;
import org.apache.pdfbox.pdmodel.common.PDRectangle;
import org.apache.pdfbox.pdmodel.common.PDStream;
import org.apache.pdfbox.pdmodel.font.PDFont;
import org.apache.pdfbox.pdmodel.font.PDFontDescriptor;
import org.apache.pdfbox.pdmodel.graphics.PDXObject;
import org.apache.pdfbox.pdmodel.graphics.form.PDFormXObject;
import org.apache.pdfbox.pdmodel.graphics.image.PDImageXObject;
import org.apache.pdfbox.pdmodel.interactive.action.PDActionURI;
import org.apache.pdfbox.pdmodel.interactive.annotation.PDAnnotation;
import org.apache.pdfbox.pdmodel.interactive.annotation.PDAnnotationLink;
import org.apache.pdfbox.pdmodel.interactive.documentnavigation.outline.PDDocumentOutline;
import org.apache.pdfbox.pdmodel.interactive.documentnavigation.outline.PDOutlineItem;
import org.apache.pdfbox.pdmodel.interactive.form.PDAcroForm;
import org.apache.pdfbox.pdmodel.interactive.form.PDField;
import org.apache.pdfbox.rendering.ImageType;
import org.apache.pdfbox.rendering.PDFRenderer;
import org.apache.pdfbox.text.PDFTextStripper;
import org.apache.pdfbox.text.TextPosition;

import java.awt.image.BufferedImage;
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.IdentityHashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

/** Independent semantic gate. This class uses PDFBox only; it never calls OpenPDF. */
public final class PdfBoxValidatorMain {
    private PdfBoxValidatorMain() {
    }

    public static void main(String[] args) {
        Path root = null;
        try {
            if (args.length != 2 || !"--job-dir".equals(args[0])) {
                return;
            }
            root = Path.of(args[1]).toAbsolutePath().normalize();
            validate(root);
        } catch (ValidationFailure error) {
            if (root != null) {
                write(root, false, error.code(), null, 0);
            }
        } catch (Exception error) {
            if (root != null) {
                write(root, false, "validator_internal", null, 0);
            }
        }
    }

    private static void validate(Path root) throws Exception {
        long validationStarted = System.nanoTime();
        Map<String, Double> timings = new LinkedHashMap<>();
        long phaseStarted = validationStarted;
        ContractSupport.Job job;
        try {
            job = ContractSupport.readJob(root.resolve("job.json"));
        } catch (ContractSupport.ContractException error) {
            throw new ValidationFailure("invalid_contract");
        }
        Path sourcePath = regular(root.resolve("source.pdf"));
        Path derivativePath = regular(root.resolve("quarantine").resolve("derivative.pdf"));
        if (!ContractSupport.sha256(sourcePath).equals(job.source().sha256())) {
            throw new ValidationFailure("stale_source");
        }
        if (Files.size(derivativePath) > job.limits().maxOutputBytes()) {
            throw new ValidationFailure("resource_limit");
        }
        phaseStarted = record(timings, "contract_and_limits_ms", phaseStarted);
        PDDocument source = Loader.loadPDF(sourcePath.toFile());
        PDDocument derivative;
        try {
            derivative = Loader.loadPDF(derivativePath.toFile());
        } catch (Exception error) {
            source.close();
            throw error;
        }
        phaseStarted = record(timings, "pdf_reopen_ms", phaseStarted);
        try (source; derivative) {
            int sourcePages = source.getNumberOfPages();
            int outputPages = derivative.getNumberOfPages();
            if (sourcePages != job.source().pageCount() || outputPages < sourcePages
                    || outputPages > job.limits().maxPages() + 256) {
                throw new ValidationFailure("page_count");
            }
            Snapshot before = snapshot(source, sourcePages);
            Snapshot after = snapshot(derivative, sourcePages);
            if (!sameSourceSemantics(before, after)) {
                throw new ValidationFailure("source_semantics");
            }
            phaseStarted = record(timings, "semantic_preservation_ms", phaseStarted);
            verifySourceContentStreams(source, derivative);
            phaseStarted = record(timings, "source_streams_ms", phaseStarted);
            List<String> sourceText = pageText(source);
            List<String> derivativeText = pageText(derivative);
            phaseStarted = record(timings, "text_extraction_ms", phaseStarted);
            verifySourceText(sourceText, derivativeText);
            verifyGeometry(job, source, derivative);
            phaseStarted = record(timings, "page_geometry_ms", phaseStarted);
            Map<Integer, List<ContractSupport.Line>> inlineLines = inlineLines(job);
            Map<Integer, GeneratedPageText> generatedPages = generatedPages(
                    inlineLines, source, derivative);
            phaseStarted = record(timings, "generated_text_extraction_ms", phaseStarted);
            verifyGeneratedText(inlineLines, generatedPages);
            verifyPlacement(inlineLines, generatedPages);
            phaseStarted = record(timings, "coordinates_ms", phaseStarted);
            verifyContinuation(job, derivativeText, sourcePages);
            phaseStarted = record(timings, "continuation_ms", phaseStarted);
            renderAllPages(derivative);
            phaseStarted = record(timings, "rendering_ms", phaseStarted);
            write(root, true, null, job.jobId(), outputPages);
            writeProfile(root, timings, elapsedMillis(validationStarted));
        } catch (ValidationFailure error) {
            throw error;
        } catch (Exception error) {
            throw new ValidationFailure("pdf_reopen_or_render");
        }
    }

    private static void verifyGeometry(
            ContractSupport.Job job, PDDocument source, PDDocument output) throws ValidationFailure {
        for (ContractSupport.PageGeometry expected : job.pages()) {
            PDPage sourcePage = source.getPage(expected.pageNumber() - 1);
            PDPage outputPage = output.getPage(expected.pageNumber() - 1);
            if (!pageMatches(expected, sourcePage) || !pageMatches(expected, outputPage)) {
                throw new ValidationFailure("page_geometry");
            }
        }
    }

    private static boolean sameSourceSemantics(Snapshot before, Snapshot after) {
        return before.pages().equals(after.pages())
                && before.annotations().equals(after.annotations())
                && before.formFields().equals(after.formFields())
                && before.outlines().equals(after.outlines())
                && before.info().equals(after.info())
                && before.xmpSha256().equals(after.xmpSha256())
                && before.encrypted() == after.encrypted()
                && before.permissions().equals(after.permissions())
                && after.imageHashes().containsAll(before.imageHashes())
                && after.embeddedFontHashes().containsAll(before.embeddedFontHashes());
    }

    private static boolean pageMatches(ContractSupport.PageGeometry expected, PDPage page) {
        return Math.floorMod(page.getRotation(), 360) == expected.rotation()
                && Math.abs(page.getUserUnit() - expected.userUnit()) < 0.000_001
                && boxMatches(page.getMediaBox(), expected.mediaBoxMpt(), expected.userUnit())
                && boxMatches(page.getCropBox(), expected.cropBoxMpt(), expected.userUnit());
    }

    private static boolean boxMatches(PDRectangle box, int[] expected, double userUnit) {
        double[] actual = {box.getLowerLeftX(), box.getLowerLeftY(),
                box.getUpperRightX(), box.getUpperRightY()};
        for (int index = 0; index < actual.length; index++) {
            if (Math.abs(actual[index] * userUnit * 1000 - expected[index]) > 1.1) {
                return false;
            }
        }
        return true;
    }

    private static void verifySourceContentStreams(PDDocument source, PDDocument output)
            throws IOException, ValidationFailure {
        for (int index = 0; index < source.getNumberOfPages(); index++) {
            Map<String, Integer> expected = streamDigests(source.getPage(index));
            Map<String, Integer> actual = streamDigests(output.getPage(index));
            for (Map.Entry<String, Integer> item : expected.entrySet()) {
                if (actual.getOrDefault(item.getKey(), 0) < item.getValue()) {
                    throw new ValidationFailure("source_content_stream");
                }
            }
        }
    }

    private static Map<String, Integer> streamDigests(PDPage page) throws IOException {
        Map<String, Integer> result = new HashMap<>();
        var streams = page.getContentStreams();
        while (streams.hasNext()) {
            PDStream stream = streams.next();
            String hash;
            try (InputStream input = stream.createInputStream()) {
                hash = digest(input);
            }
            result.merge(hash, 1, Integer::sum);
        }
        return result;
    }

    private static void verifySourceText(List<String> expected, List<String> actual)
            throws ValidationFailure {
        for (int index = 0; index < expected.size(); index++) {
            if (!runsInOrder(expected.get(index), actual.get(index))) {
                throw new ValidationFailure("source_text");
            }
        }
    }

    private static Map<Integer, List<ContractSupport.Line>> inlineLines(ContractSupport.Job job) {
        Map<Integer, List<ContractSupport.Line>> expectedByPage = new HashMap<>();
        for (ContractSupport.Answer answer : job.answers()) {
            if (answer.classification().equals("inline")) {
                expectedByPage.computeIfAbsent(answer.pageNumber() - 1, ignored -> new ArrayList<>())
                        .addAll(answer.lines());
            }
        }
        return expectedByPage;
    }

    private static Map<Integer, GeneratedPageText> generatedPages(
            Map<Integer, List<ContractSupport.Line>> expectedByPage,
            PDDocument source, PDDocument output) throws IOException {
        Map<Integer, GeneratedPageText> result = new HashMap<>();
        for (Map.Entry<Integer, List<ContractSupport.Line>> entry : expectedByPage.entrySet()) {
            int pageIndex = entry.getKey();
            result.put(pageIndex, generatedPageText(
                    source.getPage(pageIndex), output.getPage(pageIndex), output, pageIndex + 1));
        }
        return result;
    }

    private static void verifyGeneratedText(
            Map<Integer, List<ContractSupport.Line>> expectedByPage,
            Map<Integer, GeneratedPageText> generatedPages) throws ValidationFailure {
        for (Map.Entry<Integer, List<ContractSupport.Line>> entry : expectedByPage.entrySet()) {
            String expected = entry.getValue().stream()
                    .map(ContractSupport.Line::text)
                    .collect(java.util.stream.Collectors.joining());
            if (!generatedPages.get(entry.getKey()).characters().equals(expected)) {
                throw new ValidationFailure("generated_text_exact");
            }
        }
    }

    private static void verifyPlacement(
            Map<Integer, List<ContractSupport.Line>> expectedByPage,
            Map<Integer, GeneratedPageText> generatedPages) throws ValidationFailure {
        for (Map.Entry<Integer, List<ContractSupport.Line>> entry : expectedByPage.entrySet()) {
            GeneratedPageText page = generatedPages.get(entry.getKey());
            int offset = 0;
            for (ContractSupport.Line line : entry.getValue()) {
                if (line.text().isEmpty()) {
                    continue;
                }
                GlyphPosition position = page.positionAt(offset);
                double expectedX = line.xMpt() / 1000.0;
                double expectedY = line.baselineYMpt() / 1000.0;
                if (Math.hypot(position.x() - expectedX, position.y() - expectedY) > 1.25) {
                    throw new ValidationFailure("placement_exact");
                }
                offset += line.text().length();
            }
        }
    }

    private static GeneratedPageText generatedPageText(
            PDPage sourcePage, PDPage outputPage, PDDocument document, int pageNumber)
            throws IOException {
        Map<String, Integer> remainingSource = streamDigests(sourcePage);
        List<COSStream> generated = new ArrayList<>();
        var streams = outputPage.getContentStreams();
        while (streams.hasNext()) {
            PDStream stream = streams.next();
            String hash;
            try (InputStream input = stream.createInputStream()) {
                hash = digest(input);
            }
            int count = remainingSource.getOrDefault(hash, 0);
            if (count > 0) {
                remainingSource.put(hash, count - 1);
            } else {
                generated.add(stream.getCOSObject());
            }
        }
        if (generated.isEmpty()) {
            return new GeneratedPageText("", List.of());
        }
        COSBase original = outputPage.getCOSObject().getItem(COSName.CONTENTS);
        COSArray onlyGenerated = new COSArray();
        generated.forEach(onlyGenerated::add);
        outputPage.getCOSObject().setItem(COSName.CONTENTS, onlyGenerated);
        try {
            PositionStripper stripper = new PositionStripper();
            stripper.setSortByPosition(false);
            stripper.setStartPage(pageNumber);
            stripper.setEndPage(pageNumber);
            stripper.getText(document);
            return stripper.result();
        } finally {
            outputPage.getCOSObject().setItem(COSName.CONTENTS, original);
        }
    }

    private static void verifyContinuation(
            ContractSupport.Job job, List<String> text, int sourcePages)
            throws ValidationFailure {
        List<ContractSupport.Answer> appendices = job.answers().stream()
                .filter(answer -> answer.classification().equals("appendix"))
                .toList();
        if (appendices.isEmpty()) {
            if (text.size() != sourcePages) {
                throw new ValidationFailure("continuation_order");
            }
            return;
        }
        if (text.size() <= sourcePages) {
            throw new ValidationFailure("continuation_order");
        }
        String continuationText = String.join("\n", text.subList(sourcePages, text.size()));
        int cursor = 0;
        for (ContractSupport.Answer answer : appendices) {
            int identifier = continuationText.indexOf(answer.displayIdentifier(), cursor);
            if (identifier < 0
                    || !tokensInOrder(answer.committedText(), continuationText.substring(identifier))
                    || !tokensInOrder(answer.continuation().sourceQuestion(),
                    continuationText.substring(identifier))) {
                throw new ValidationFailure("continuation_content");
            }
            cursor = identifier + answer.displayIdentifier().length();
        }
        for (int page = sourcePages + 1; page <= text.size(); page++) {
            String expected = "Attached answer page " + (page - sourcePages);
            if (!text.get(page - 1).contains(expected)) {
                throw new ValidationFailure("continuation_numbering");
            }
        }
    }

    private static boolean tokensInOrder(String expected, String actual) {
        String[] expectedTokens = expected.strip().split("\\s+");
        String[] actualTokens = actual.strip().split("\\s+");
        int cursor = 0;
        for (String token : expectedTokens) {
            while (cursor < actualTokens.length && !actualTokens[cursor].equals(token)) {
                cursor++;
            }
            if (cursor == actualTokens.length) {
                return false;
            }
            cursor++;
        }
        return true;
    }

    private static void renderAllPages(PDDocument document) throws IOException, ValidationFailure {
        PDFRenderer renderer = new PDFRenderer(document);
        for (int index = 0; index < document.getNumberOfPages(); index++) {
            BufferedImage image = renderer.renderImageWithDPI(index, 36, ImageType.RGB);
            if (image.getWidth() < 1 || image.getHeight() < 1) {
                throw new ValidationFailure("pdf_reopen_or_render");
            }
        }
    }

    private static Snapshot snapshot(PDDocument document, int sourcePageCount) throws IOException {
        List<PageSnapshot> pages = new ArrayList<>();
        List<String> annotations = new ArrayList<>();
        Set<String> imageHashes = new HashSet<>();
        Set<String> fontHashes = new HashSet<>();
        Set<COSBase> visited = Collections.newSetFromMap(new IdentityHashMap<>());
        for (int pageIndex = 0; pageIndex < sourcePageCount; pageIndex++) {
            PDPage page = document.getPage(pageIndex);
            pages.add(new PageSnapshot(
                    rectangle(page.getMediaBox()), rectangle(page.getCropBox()),
                    rectangle(page.getTrimBox()), rectangle(page.getBleedBox()),
                    rectangle(page.getArtBox()), Math.floorMod(page.getRotation(), 360),
                    page.getUserUnit()));
            int annotationIndex = 0;
            for (PDAnnotation annotation : page.getAnnotations()) {
                annotationIndex++;
                String action = "";
                if (annotation instanceof PDAnnotationLink link
                        && link.getAction() instanceof PDActionURI uri) {
                    action = nullToEmpty(uri.getURI());
                }
                annotations.add((pageIndex + 1) + ":" + annotationIndex + ":"
                        + annotation.getSubtype() + ":" + rectangle(annotation.getRectangle()) + ":"
                        + nullToEmpty(annotation.getContents()) + ":" + action);
            }
            collectResources(page.getResources(), imageHashes, fontHashes, visited);
        }
        List<String> fields = new ArrayList<>();
        PDAcroForm form = document.getDocumentCatalog().getAcroForm();
        if (form != null) {
            for (PDField field : form.getFieldTree()) {
                fields.add(field.getFullyQualifiedName() + ":" + field.getFieldType() + ":"
                        + field.getFieldFlags() + ":" + field.getValueAsString());
            }
        }
        Map<String, String> info = new LinkedHashMap<>();
        PDDocumentInformation information = document.getDocumentInformation();
        for (String key : new TreeSet<>(information.getMetadataKeys())) {
            Object value = information.getPropertyStringValue(key);
            info.put(key, value == null ? "" : value.toString());
        }
        String xmp = "";
        PDMetadata metadata = document.getDocumentCatalog().getMetadata();
        if (metadata != null) {
            try (InputStream input = metadata.exportXMPMetadata()) {
                xmp = digest(input);
            }
        }
        return new Snapshot(
                List.copyOf(pages), List.copyOf(annotations), List.copyOf(fields),
                outlines(document.getDocumentCatalog().getDocumentOutline()), Map.copyOf(info), xmp,
                document.isEncrypted(), permissionSignature(document), Set.copyOf(imageHashes),
                Set.copyOf(fontHashes));
    }

    private static void collectResources(
            PDResources resources, Set<String> imageHashes, Set<String> fontHashes,
            Set<COSBase> visited) throws IOException {
        if (resources == null || !visited.add(resources.getCOSObject())) {
            return;
        }
        for (COSName name : resources.getFontNames()) {
            PDFont font = resources.getFont(name);
            PDFontDescriptor descriptor = font.getFontDescriptor();
            if (descriptor == null) {
                continue;
            }
            PDStream stream = descriptor.getFontFile2();
            if (stream == null) stream = descriptor.getFontFile3();
            if (stream == null) stream = descriptor.getFontFile();
            if (stream != null) {
                try (InputStream input = stream.createInputStream()) {
                    fontHashes.add(digest(input));
                }
            }
        }
        for (COSName name : resources.getXObjectNames()) {
            PDXObject object = resources.getXObject(name);
            if (object instanceof PDImageXObject image) {
                imageHashes.add(digestImage(image.getImage()));
            } else if (object instanceof PDFormXObject form) {
                collectResources(form.getResources(), imageHashes, fontHashes, visited);
            }
        }
    }

    private static List<String> outlines(PDDocumentOutline root) {
        if (root == null) return List.of();
        List<String> values = new ArrayList<>();
        collectOutlineChildren(root.getFirstChild(), "", values);
        return List.copyOf(values);
    }

    private static void collectOutlineChildren(PDOutlineItem item, String prefix, List<String> values) {
        for (PDOutlineItem current = item; current != null; current = current.getNextSibling()) {
            values.add(prefix + current.getTitle());
            collectOutlineChildren(current.getFirstChild(), prefix + "/", values);
        }
    }

    private static List<String> pageText(PDDocument document) throws IOException {
        PDFTextStripper stripper = new PDFTextStripper();
        stripper.setSortByPosition(false);
        List<String> pages = new ArrayList<>();
        for (int page = 1; page <= document.getNumberOfPages(); page++) {
            stripper.setStartPage(page);
            stripper.setEndPage(page);
            pages.add(stripper.getText(document).replace("\r\n", "\n").replace('\r', '\n'));
        }
        return pages;
    }

    private static boolean runsInOrder(String expected, String actual) {
        int cursor = 0;
        for (String line : expected.split("\\R", -1)) {
            String run = line.strip();
            if (run.isEmpty()) continue;
            int found = actual.indexOf(run, cursor);
            if (found < 0) return false;
            cursor = found + run.length();
        }
        return true;
    }

    private static String permissionSignature(PDDocument document) {
        var permission = document.getCurrentAccessPermission();
        return String.join(",", Boolean.toString(permission.canPrint()),
                Boolean.toString(permission.canModify()), Boolean.toString(permission.canExtractContent()),
                Boolean.toString(permission.canModifyAnnotations()), Boolean.toString(permission.canFillInForm()),
                Boolean.toString(permission.canExtractForAccessibility()),
                Boolean.toString(permission.canAssembleDocument()), Boolean.toString(permission.canPrintFaithful()));
    }

    private static List<Double> rectangle(PDRectangle rectangle) {
        if (rectangle == null) return List.of();
        return List.of((double) rectangle.getLowerLeftX(), (double) rectangle.getLowerLeftY(),
                (double) rectangle.getUpperRightX(), (double) rectangle.getUpperRightY());
    }

    private static String digestImage(BufferedImage image) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            digest.update(ByteBuffer.allocate(8).putInt(image.getWidth()).putInt(image.getHeight()).array());
            int[] row = new int[image.getWidth()];
            ByteBuffer bytes = ByteBuffer.allocate(row.length * Integer.BYTES);
            for (int y = 0; y < image.getHeight(); y++) {
                image.getRGB(0, y, image.getWidth(), 1, row, 0, image.getWidth());
                bytes.clear();
                for (int pixel : row) bytes.putInt(pixel);
                digest.update(bytes.array());
            }
            return HexFormat.of().formatHex(digest.digest());
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException(error);
        }
    }

    private static String digest(InputStream input) throws IOException {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] buffer = new byte[64 * 1024];
            int count;
            while ((count = input.read(buffer)) >= 0) digest.update(buffer, 0, count);
            return HexFormat.of().formatHex(digest.digest());
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException(error);
        }
    }

    private static Path regular(Path path) throws ValidationFailure {
        if (!Files.isRegularFile(path) || Files.isSymbolicLink(path)) {
            throw new ValidationFailure("missing_artifact");
        }
        return path;
    }

    private static void write(Path root, boolean success, String code, String jobId, int pageCount) {
        try {
            ObjectNode status = ContractSupport.MAPPER.createObjectNode();
            status.put("schema_version", 1);
            if (success) {
                status.put("status", "ok");
                status.put("job_id", jobId);
                status.put("validator", "pdfbox");
                status.put("page_count", pageCount);
                status.put("generated_text_exact", true);
                status.put("placement_exact", true);
                status.put("source_preserved", true);
                status.put("rendered_pages", pageCount);
            } else {
                status.put("status", "fail");
                status.put("code", code);
            }
            Files.write(root.resolve("pdfbox-status.json"),
                    ContractSupport.MAPPER.writeValueAsBytes(status));
        } catch (IOException ignored) {
            // Missing status is also a closed validation failure.
        }
    }

    private static long record(Map<String, Double> timings, String name, long started) {
        long now = System.nanoTime();
        timings.put(name, (now - started) / 1_000_000.0);
        return now;
    }

    private static double elapsedMillis(long started) {
        return (System.nanoTime() - started) / 1_000_000.0;
    }

    private static void writeProfile(Path root, Map<String, Double> timings, double totalMillis) {
        try {
            ObjectNode profile = ContractSupport.MAPPER.createObjectNode();
            profile.put("schema_version", 1);
            ObjectNode phases = profile.putObject("phases_ms");
            timings.forEach(phases::put);
            profile.put("validator_internal_total_ms", totalMillis);
            Files.write(root.resolve("pdfbox-profile.json"),
                    ContractSupport.MAPPER.writeValueAsBytes(profile));
        } catch (IOException ignored) {
            // Profiling evidence is non-authoritative and never affects validation.
        }
    }

    private static String nullToEmpty(String value) {
        return value == null ? "" : value;
    }

    private record Snapshot(
            List<PageSnapshot> pages, List<String> annotations, List<String> formFields,
            List<String> outlines, Map<String, String> info, String xmpSha256,
            boolean encrypted, String permissions, Set<String> imageHashes,
            Set<String> embeddedFontHashes) {
    }

    private record PageSnapshot(
            List<Double> mediaBox, List<Double> cropBox, List<Double> trimBox,
            List<Double> bleedBox, List<Double> artBox, int rotation, float userUnit) {
    }

    private record GlyphPosition(String text, float x, float y) {
    }

    private record GeneratedPageText(String characters, List<GlyphPosition> positions) {
        GlyphPosition positionAt(int characterOffset) throws ValidationFailure {
            int offset = 0;
            for (GlyphPosition position : positions) {
                int end = offset + position.text().length();
                if (characterOffset >= offset && characterOffset < end) return position;
                offset = end;
            }
            throw new ValidationFailure("placement_exact");
        }
    }

    private static final class PositionStripper extends PDFTextStripper {
        private final StringBuilder text = new StringBuilder();
        private final List<GlyphPosition> positions = new ArrayList<>();

        PositionStripper() throws IOException {
        }

        @Override
        protected void processTextPosition(TextPosition position) {
            String unicode = position.getUnicode();
            if (unicode != null) {
                text.append(unicode);
                positions.add(new GlyphPosition(unicode, position.getXDirAdj(), position.getYDirAdj()));
            }
            super.processTextPosition(position);
        }

        GeneratedPageText result() {
            return new GeneratedPageText(text.toString(), List.copyOf(positions));
        }
    }

    private static final class ValidationFailure extends Exception {
        private final String code;

        ValidationFailure(String code) {
            super(code);
            this.code = code;
        }

        String code() {
            return code;
        }
    }
}
