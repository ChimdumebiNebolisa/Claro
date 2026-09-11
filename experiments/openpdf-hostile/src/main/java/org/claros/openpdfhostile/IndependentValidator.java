package org.claros.openpdfhostile;

import org.apache.pdfbox.Loader;
import org.apache.pdfbox.cos.COSBase;
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

import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.IdentityHashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class IndependentValidator {
    private static final float RENDER_DPI = 96;
    private static final float COORDINATE_DPI = 288;

    public ValidationResult validate(
            FixtureSpec spec,
            Path sourcePath,
            OpenPdfSpike.OpenResult openResult) throws IOException {
        String password = spec.encrypted() ? spec.userPassword() : "";
        try (PDDocument source = Loader.loadPDF(sourcePath.toFile(), password);
             PDDocument derivative = Loader.loadPDF(openResult.derivative().toFile(), password)) {
            Snapshot sourceSnapshot = snapshot(source);
            Snapshot outputSnapshot = snapshot(derivative);
            List<String> losses = new ArrayList<>();

            int expectedPages = source.getNumberOfPages() + openResult.continuationPages();
            if (derivative.getNumberOfPages() != expectedPages) {
                losses.add("page count changed unexpectedly: expected " + expectedPages
                        + ", got " + derivative.getNumberOfPages());
            }
            if (!sourceSnapshot.pages().equals(
                    outputSnapshot.pages().subList(0, Math.min(
                            sourceSnapshot.pages().size(), outputSnapshot.pages().size())))) {
                losses.add("source page dimensions, rotation, UserUnit, or page boxes changed");
            }
            if (!sourceSnapshot.annotations().equals(outputSnapshot.annotations())) {
                losses.add("annotations or link annotations changed");
            }
            if (!sourceSnapshot.formFields().equals(outputSnapshot.formFields())) {
                losses.add("AcroForm field definitions or values changed");
            }
            if (!sourceSnapshot.outlines().equals(outputSnapshot.outlines())) {
                losses.add("bookmarks/outlines changed");
            }
            if (!sourceSnapshot.info().equals(outputSnapshot.info())) {
                losses.add("document information metadata changed");
            }
            if (!sourceSnapshot.xmpSha256().equals(outputSnapshot.xmpSha256())) {
                losses.add("XMP metadata changed");
            }
            if (sourceSnapshot.encrypted() != outputSnapshot.encrypted()) {
                losses.add("encryption state changed");
            }
            if (!sourceSnapshot.permissions().equals(outputSnapshot.permissions())) {
                losses.add("encryption permissions changed");
            }
            if (!outputSnapshot.imageHashes().containsAll(sourceSnapshot.imageHashes())) {
                losses.add("one or more source images changed or disappeared");
            }
            if (!outputSnapshot.embeddedFontHashes().containsAll(sourceSnapshot.embeddedFontHashes())) {
                losses.add("one or more embedded source font programs changed or disappeared");
            }

            List<String> sourcePageText = pageText(source);
            List<String> outputPageText = pageText(derivative);
            for (int index = 0; index < sourcePageText.size() && index < outputPageText.size(); index++) {
                if (!textRunsPresentInOrder(sourcePageText.get(index), outputPageText.get(index))) {
                    losses.add("source text is not preserved in order on page " + (index + 1));
                }
            }

            long outsideMaskDifferences = compareSourcePagePixels(
                    source,
                    derivative,
                    openResult.placements());
            if (outsideMaskDifferences != 0) {
                losses.add(outsideMaskDifferences + " rendered pixels changed outside approved overlay masks");
            }

            CoordinateResult coordinates = validateCoordinateMarkers(
                    derivative,
                    openResult.placements());
            boolean overlayTextPresent = true;
            List<String> missingOverlayText = new ArrayList<>();
            for (PhysicalPlacement placement : openResult.placements()) {
                String actual = outputPageText.get(placement.pageNumber() - 1);
                if (!actual.contains(placement.text())) {
                    overlayTextPresent = false;
                    missingOverlayText.add(placement.id());
                }
            }

            ContinuationResult continuation = spec.continuation()
                    ? validateContinuation(source.getNumberOfPages(), derivative, openResult)
                    : new ContinuationResult(Status.NOT_APPLICABLE, List.of());
            return new ValidationResult(
                    losses.isEmpty(),
                    overlayTextPresent,
                    coordinates.correct(),
                    outsideMaskDifferences,
                    Collections.unmodifiableList(losses),
                    Collections.unmodifiableList(missingOverlayText),
                    coordinates.details(),
                    continuation.status(),
                    continuation.details(),
                    sourceSnapshot,
                    outputSnapshot);
        }
    }

    private static Snapshot snapshot(PDDocument document) throws IOException {
        List<PageSnapshot> pages = new ArrayList<>();
        List<String> annotations = new ArrayList<>();
        Set<String> imageHashes = new HashSet<>();
        Set<String> fontHashes = new HashSet<>();
        Set<COSBase> visitedResources = Collections.newSetFromMap(new IdentityHashMap<>());
        int pageIndex = 0;
        for (PDPage page : document.getPages()) {
            pageIndex++;
            pages.add(new PageSnapshot(
                    rectangle(page.getMediaBox()),
                    rectangle(page.getCropBox()),
                    rectangle(page.getTrimBox()),
                    rectangle(page.getBleedBox()),
                    rectangle(page.getArtBox()),
                    Math.floorMod(page.getRotation(), 360),
                    page.getUserUnit()));
            int annotationIndex = 0;
            for (PDAnnotation annotation : page.getAnnotations()) {
                annotationIndex++;
                String action = "";
                if (annotation instanceof PDAnnotationLink link
                        && link.getAction() instanceof PDActionURI uri) {
                    action = uri.getURI();
                }
                annotations.add(pageIndex + ":" + annotationIndex + ":" + annotation.getSubtype()
                        + ":" + rectangle(annotation.getRectangle())
                        + ":" + nullToEmpty(annotation.getContents())
                        + ":" + action);
            }
            collectResources(page.getResources(), imageHashes, fontHashes, visitedResources);
        }

        List<String> fields = new ArrayList<>();
        PDAcroForm form = document.getDocumentCatalog().getAcroForm();
        if (form != null) {
            for (PDField field : form.getFieldTree()) {
                fields.add(field.getFullyQualifiedName() + ":" + field.getFieldType()
                        + ":" + field.getFieldFlags() + ":" + field.getValueAsString());
            }
        }
        List<String> outlines = outlines(document.getDocumentCatalog().getDocumentOutline());
        Map<String, String> info = new LinkedHashMap<>();
        PDDocumentInformation information = document.getDocumentInformation();
        for (String key : new java.util.TreeSet<>(information.getMetadataKeys())) {
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
                List.copyOf(pages),
                List.copyOf(annotations),
                List.copyOf(fields),
                List.copyOf(outlines),
                Map.copyOf(info),
                xmp,
                document.isEncrypted(),
                permissionSignature(document),
                Set.copyOf(imageHashes),
                Set.copyOf(fontHashes));
    }

    private static void collectResources(
            PDResources resources,
            Set<String> imageHashes,
            Set<String> fontHashes,
            Set<COSBase> visited) throws IOException {
        if (resources == null || !visited.add(resources.getCOSObject())) {
            return;
        }
        for (var name : resources.getFontNames()) {
            PDFont font = resources.getFont(name);
            PDFontDescriptor descriptor = font.getFontDescriptor();
            if (descriptor == null) {
                continue;
            }
            PDStream stream = descriptor.getFontFile2();
            if (stream == null) {
                stream = descriptor.getFontFile3();
            }
            if (stream == null) {
                stream = descriptor.getFontFile();
            }
            if (stream != null) {
                try (InputStream input = stream.createInputStream()) {
                    fontHashes.add(digest(input));
                }
            }
        }
        for (var name : resources.getXObjectNames()) {
            PDXObject object = resources.getXObject(name);
            if (object instanceof PDImageXObject image) {
                imageHashes.add(digestImage(image.getImage()));
            } else if (object instanceof PDFormXObject form) {
                collectResources(form.getResources(), imageHashes, fontHashes, visited);
            }
        }
    }

    private static List<String> outlines(PDDocumentOutline root) {
        if (root == null) {
            return List.of();
        }
        List<String> values = new ArrayList<>();
        collectOutlineChildren(root.getFirstChild(), "", values);
        return List.copyOf(values);
    }

    private static void collectOutlineChildren(
            PDOutlineItem item,
            String prefix,
            List<String> values) {
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
            pages.add(normalizeLineEndings(stripper.getText(document)));
        }
        return List.copyOf(pages);
    }

    private static boolean textRunsPresentInOrder(String expected, String actual) {
        int cursor = 0;
        for (String line : expected.split("\\n", -1)) {
            String run = line.strip();
            if (run.isEmpty()) {
                continue;
            }
            int found = actual.indexOf(run, cursor);
            if (found < 0) {
                return false;
            }
            cursor = found + run.length();
        }
        return true;
    }

    private static long compareSourcePagePixels(
            PDDocument source,
            PDDocument derivative,
            List<PhysicalPlacement> placements) throws IOException {
        PDFRenderer sourceRenderer = new PDFRenderer(source);
        PDFRenderer derivativeRenderer = new PDFRenderer(derivative);
        long differences = 0;
        for (int pageIndex = 0; pageIndex < source.getNumberOfPages(); pageIndex++) {
            int pageNumber = pageIndex + 1;
            BufferedImage before = sourceRenderer.renderImageWithDPI(pageIndex, RENDER_DPI, ImageType.RGB);
            BufferedImage after = derivativeRenderer.renderImageWithDPI(pageIndex, RENDER_DPI, ImageType.RGB);
            if (before.getWidth() != after.getWidth() || before.getHeight() != after.getHeight()) {
                differences += (long) Math.max(before.getWidth(), after.getWidth())
                        * Math.max(before.getHeight(), after.getHeight());
                continue;
            }
            PDPage sourcePage = source.getPage(pageIndex);
            List<PixelMask> masks = placements.stream()
                    .filter(placement -> placement.pageNumber() == pageNumber)
                    .map(placement -> pixelMask(
                            placement,
                            sourcePage,
                            before))
                    .toList();
            for (int y = 0; y < before.getHeight(); y++) {
                for (int x = 0; x < before.getWidth(); x++) {
                    if (before.getRGB(x, y) != after.getRGB(x, y)
                            && !insideAnyMask(masks, x, y)) {
                        differences++;
                    }
                }
            }
        }
        return differences;
    }

    private static boolean insideAnyMask(List<PixelMask> masks, int x, int y) {
        for (PixelMask mask : masks) {
            if (mask.contains(x, y)) {
                return true;
            }
        }
        return false;
    }

    private static PixelMask pixelMask(
            PhysicalPlacement placement,
            PDPage page,
            BufferedImage image) {
        RenderScale scale = renderScale(page, image);
        double padding = 6;
        return new PixelMask(
                (int) Math.floor((placement.xPt() - padding) * scale.x()),
                (int) Math.floor((placement.baselineFromTopPt()
                        - placement.maskHeightPt() - padding) * scale.y()),
                (int) Math.ceil((placement.xPt() + placement.maskWidthPt() + padding) * scale.x()),
                (int) Math.ceil((placement.baselineFromTopPt() + padding) * scale.y()));
    }

    private static CoordinateResult validateCoordinateMarkers(
            PDDocument derivative,
            List<PhysicalPlacement> placements) throws IOException {
        PDFRenderer renderer = new PDFRenderer(derivative);
        Map<Integer, BufferedImage> pages = new java.util.HashMap<>();
        List<String> details = new ArrayList<>();
        boolean correct = true;
        for (PhysicalPlacement placement : placements) {
            BufferedImage image = pages.computeIfAbsent(placement.pageNumber(), page -> {
                try {
                    return renderer.renderImageWithDPI(page - 1, COORDINATE_DPI, ImageType.RGB);
                } catch (IOException error) {
                    throw new RenderRuntimeException(error);
                }
            });
            PDPage page = derivative.getPage(placement.pageNumber() - 1);
            RenderScale scale = renderScale(page, image);
            int centerX = (int) Math.round(placement.xPt() * scale.x());
            int centerY = (int) Math.round(placement.baselineFromTopPt() * scale.y());
            List<int[]> magenta = new ArrayList<>();
            int radiusX = (int) Math.ceil(5 * scale.x());
            int radiusY = (int) Math.ceil(5 * scale.y());
            for (int y = Math.max(0, centerY - radiusY);
                 y <= Math.min(image.getHeight() - 1, centerY + radiusY); y++) {
                for (int x = Math.max(0, centerX - radiusX);
                     x <= Math.min(image.getWidth() - 1, centerX + radiusX); x++) {
                    int rgb = image.getRGB(x, y);
                    int red = (rgb >>> 16) & 0xff;
                    int green = (rgb >>> 8) & 0xff;
                    int blue = rgb & 0xff;
                    if (red >= 220 && green <= 45 && blue >= 220) {
                        magenta.add(new int[]{x, y});
                    }
                }
            }
            if (magenta.isEmpty()) {
                correct = false;
                details.add(placement.id() + ": no coordinate marker near intended physical point");
                continue;
            }
            double observedX = magenta.stream().mapToInt(point -> point[0]).average().orElseThrow() / scale.x();
            double observedY = magenta.stream().mapToInt(point -> point[1]).average().orElseThrow() / scale.y();
            double delta = Math.hypot(observedX - placement.xPt(), observedY - placement.baselineFromTopPt());
            if (delta > 1.75) {
                correct = false;
                details.add(placement.id() + ": coordinate delta " + String.format("%.2fpt", delta));
            }
        }
        return new CoordinateResult(correct, List.copyOf(details));
    }

    private static RenderScale renderScale(PDPage page, BufferedImage image) {
        PDRectangle crop = page.getCropBox();
        double userUnit = page.getUserUnit();
        int rotation = Math.floorMod(page.getRotation(), 360);
        double physicalWidth = (rotation == 90 || rotation == 270
                ? crop.getHeight() : crop.getWidth()) * userUnit;
        double physicalHeight = (rotation == 90 || rotation == 270
                ? crop.getWidth() : crop.getHeight()) * userUnit;
        return new RenderScale(image.getWidth() / physicalWidth, image.getHeight() / physicalHeight);
    }

    private static ContinuationResult validateContinuation(
            int sourcePageCount,
            PDDocument derivative,
            OpenPdfSpike.OpenResult result) throws IOException {
        List<String> details = new ArrayList<>();
        if (result.continuationPages() < 2) {
            details.add("continuation content did not cross two pages");
        }
        List<String> pages = pageText(derivative);
        String continuationText = String.join("\n", pages.subList(sourcePageCount, pages.size()));
        if (!continuationText.contains(OpenPdfSpike.CONTINUATION_QUESTION_ID)) {
            details.add("question identifier missing from continuation pages");
        }
        if (!continuationText.contains(OpenPdfSpike.CONTINUATION_WORKSHEET_TITLE)) {
            details.add("worksheet title missing from continuation pages");
        }
        if (!continuationText.contains(OpenPdfSpike.CONTINUATION_SOURCE_PAGE)) {
            details.add("source page number missing from continuation pages");
        }
        if (!continuationText.contains(OpenPdfSpike.CONTINUATION_QUESTION)) {
            details.add("source question missing from continuation pages");
        }
        for (String paragraph : OpenPdfSpike.CONTINUATION_ANSWER.split("\\n\\n", -1)) {
            String start = paragraph.substring(0, Math.min(80, paragraph.length()));
            String end = paragraph.substring(Math.max(0, paragraph.length() - 80));
            if (!continuationText.contains(start) || !continuationText.contains(end)) {
                details.add("approved answer paragraph was truncated or not extractable");
                break;
            }
        }
        for (int page = 1; page <= result.continuationPages(); page++) {
            if (!pages.get(sourcePageCount + page - 1).contains("Attached answer page " + page)) {
                details.add("page number missing on continuation page " + page);
            }
        }
        return new ContinuationResult(details.isEmpty() ? Status.PASS : Status.FAIL, List.copyOf(details));
    }

    private static String permissionSignature(PDDocument document) {
        var permission = document.getCurrentAccessPermission();
        return String.join(",",
                Boolean.toString(permission.canPrint()),
                Boolean.toString(permission.canModify()),
                Boolean.toString(permission.canExtractContent()),
                Boolean.toString(permission.canModifyAnnotations()),
                Boolean.toString(permission.canFillInForm()),
                Boolean.toString(permission.canExtractForAccessibility()),
                Boolean.toString(permission.canAssembleDocument()),
                Boolean.toString(permission.canPrintFaithful()));
    }

    private static List<Double> rectangle(PDRectangle rectangle) {
        if (rectangle == null) {
            return List.of();
        }
        return List.of(
                (double) rectangle.getLowerLeftX(),
                (double) rectangle.getLowerLeftY(),
                (double) rectangle.getUpperRightX(),
                (double) rectangle.getUpperRightY());
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
                for (int pixel : row) {
                    bytes.putInt(pixel);
                }
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
            int read;
            while ((read = input.read(buffer)) >= 0) {
                digest.update(buffer, 0, read);
            }
            return HexFormat.of().formatHex(digest.digest());
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException(error);
        }
    }

    private static String normalizeLineEndings(String text) {
        return text.replace("\r\n", "\n").replace('\r', '\n');
    }

    private static String nullToEmpty(String value) {
        return value == null ? "" : value;
    }

    public record ValidationResult(
            boolean preservesSource,
            boolean overlayTextPresent,
            boolean coordinateCorrect,
            long outsideMaskPixelDifferences,
            List<String> knownLosses,
            List<String> missingOverlayText,
            List<String> coordinateDetails,
            Status continuationStatus,
            List<String> continuationDetails,
            Snapshot sourceSnapshot,
            Snapshot outputSnapshot) {
    }

    public record Snapshot(
            List<PageSnapshot> pages,
            List<String> annotations,
            List<String> formFields,
            List<String> outlines,
            Map<String, String> info,
            String xmpSha256,
            boolean encrypted,
            String permissions,
            Set<String> imageHashes,
            Set<String> embeddedFontHashes) {
    }

    public record PageSnapshot(
            List<Double> mediaBox,
            List<Double> cropBox,
            List<Double> trimBox,
            List<Double> bleedBox,
            List<Double> artBox,
            int rotation,
            float userUnit) {
    }

    private record PixelMask(int minX, int minY, int maxX, int maxY) {
        boolean contains(int x, int y) {
            return x >= minX && x <= maxX && y >= minY && y <= maxY;
        }
    }

    private record CoordinateResult(boolean correct, List<String> details) {
    }

    private record RenderScale(double x, double y) {
    }

    private record ContinuationResult(Status status, List<String> details) {
    }

    private static final class RenderRuntimeException extends RuntimeException {
        private RenderRuntimeException(IOException cause) {
            super(cause);
        }
    }
}
