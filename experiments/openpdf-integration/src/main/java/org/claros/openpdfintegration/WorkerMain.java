package org.claros.openpdfintegration;

import com.fasterxml.jackson.databind.node.ObjectNode;
import org.openpdf.text.Document;
import org.openpdf.text.DocumentException;
import org.openpdf.text.Font;
import org.openpdf.text.PageSize;
import org.openpdf.text.Paragraph;
import org.openpdf.text.Phrase;
import org.openpdf.text.Rectangle;
import org.openpdf.text.pdf.BaseFont;
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
import java.io.OutputStream;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

public final class WorkerMain {
    private static final String FONT_FILE = "NotoSans-Regular.ttf";
    private static final Set<String> SAFE_CODES = Set.of(
            "invalid_contract", "stale_source", "stale_physical_ir", "placement_changed",
            "unsupported_rtl", "unsupported_rebuilt_xref", "font_not_allowlisted",
            "unsupported_glyph", "resource_limit", "invalid_pdf");

    private WorkerMain() {
    }

    public static void main(String[] args) {
        Path jobRoot = null;
        try {
            Arguments arguments = Arguments.parse(args);
            jobRoot = arguments.jobRoot();
            render(jobRoot, arguments.fontRoot());
        } catch (WorkerRejection error) {
            if (jobRoot != null) {
                writeFailure(jobRoot, error.code());
            }
        } catch (Exception error) {
            if (jobRoot != null) {
                writeFailure(jobRoot, "internal_error");
            }
        }
    }

    private static void render(Path jobRoot, Path fontRoot) throws Exception {
        long started = System.nanoTime();
        requireDirectory(jobRoot);
        requireDirectory(fontRoot);
        ContractSupport.Job job;
        try {
            job = ContractSupport.readJob(jobRoot.resolve("job.json"));
        } catch (ContractSupport.ContractException error) {
            throw new WorkerRejection(error.code());
        }
        Path sourcePath = requireFile(jobRoot.resolve("source.pdf"));
        long sourceSize = Files.size(sourcePath);
        if (sourceSize != job.source().sizeBytes() || sourceSize > job.limits().maxInputBytes()) {
            throw new WorkerRejection("resource_limit");
        }
        if (!ContractSupport.sha256(sourcePath).equals(job.source().sha256())) {
            throw new WorkerRejection("stale_source");
        }
        Path fontPath = requireFile(fontRoot.resolve(FONT_FILE));
        if (!ContractSupport.sha256(fontPath).equals(job.fontSha256())) {
            throw new WorkerRejection("font_not_allowlisted");
        }

        byte[] sourceBytes = Files.readAllBytes(sourcePath);
        Path quarantine = jobRoot.resolve("quarantine");
        Files.createDirectory(quarantine);
        Path temporary = quarantine.resolve("derivative.tmp");
        Path derivative = quarantine.resolve("derivative.pdf");
        int continuationPages;
        boolean[] outputLimitExceeded = {false};
        try (PdfReader reader = new PdfReader(sourceBytes)) {
            if (reader.isRebuilt()) {
                throw new WorkerRejection("unsupported_rebuilt_xref");
            }
            if (reader.getNumberOfPages() != job.source().pageCount()
                    || reader.getNumberOfPages() > job.limits().maxPages()) {
                throw new WorkerRejection("stale_physical_ir");
            }
            verifyGeometry(reader, job.pages());
            BaseFont font = BaseFont.createFont(
                    fontPath.toString(), BaseFont.IDENTITY_H, BaseFont.EMBEDDED);
            verifyGlyphs(job, font);
            try (OutputStream file = Files.newOutputStream(temporary);
                 OutputStream bounded = new BoundedOutputStream(
                         file, job.limits().maxOutputBytes(), outputLimitExceeded);
                 PdfStamper stamper = new PdfStamper(reader, bounded, null, true)) {
                stamper.setRotateContents(false);
                stamper.setUpdateMetadata(false);
                stamper.setUpdateDocInfo(false);
                for (ContractSupport.Answer answer : job.answers()) {
                    if (answer.classification().equals("inline")) {
                        stampAnswer(stamper, job.pages().get(answer.pageNumber() - 1), answer, font);
                    }
                }
                byte[] continuation = createContinuation(job, fontPath);
                continuationPages = appendContinuation(stamper, reader.getNumberOfPages(), continuation);
            } catch (BoundExceededException error) {
                throw new WorkerRejection("resource_limit");
            }
        } catch (WorkerRejection error) {
            Files.deleteIfExists(temporary);
            throw error;
        } catch (Exception error) {
            if (outputLimitExceeded[0] || (Files.isRegularFile(temporary)
                    && Files.size(temporary) >= job.limits().maxOutputBytes())) {
                Files.deleteIfExists(temporary);
                throw new WorkerRejection("resource_limit");
            }
            Files.deleteIfExists(temporary);
            throw new WorkerRejection("invalid_pdf");
        }
        if (Files.size(temporary) < 8 || Files.size(temporary) > job.limits().maxOutputBytes()) {
            Files.deleteIfExists(temporary);
            throw new WorkerRejection("resource_limit");
        }
        moveAtomically(temporary, derivative);
        int outputPages = job.source().pageCount() + continuationPages;
        ObjectNode status = ContractSupport.MAPPER.createObjectNode();
        status.put("schema_version", 1);
        status.put("status", "ok");
        status.put("job_id", job.jobId());
        status.put("source_sha256", job.source().sha256());
        status.put("output_sha256", ContractSupport.sha256(derivative));
        status.put("output_bytes", Files.size(derivative));
        status.put("source_pages", job.source().pageCount());
        status.put("continuation_pages", continuationPages);
        status.put("output_pages", outputPages);
        status.put("reader_rebuilt", false);
        status.put("incremental", true);
        status.put("render_millis", (System.nanoTime() - started) / 1_000_000);
        writeStatus(jobRoot, status);
    }

    private static void stampAnswer(
            PdfStamper stamper,
            ContractSupport.PageGeometry page,
            ContractSupport.Answer answer,
            BaseFont font) {
        PdfContentByte canvas = stamper.getOverContent(answer.pageNumber());
        canvas.getPdfDocument().setGlyphSubstitutionEnabled(false);
        int[] transform = page.transform();
        for (ContractSupport.Line line : answer.lines()) {
            canvas.saveState();
            canvas.setColorFill(new Color(17, 24, 39));
            canvas.beginMarkedContentSequence(new PdfName("ClarosAnswer"));
            canvas.beginText();
            canvas.setFontAndSize(font, (float) (line.fontSizeMpt() / 1000.0 / page.userUnit()));
            canvas.setTextMatrix(
                    transform[0], transform[1], transform[2], transform[3],
                    (float) (applyX(transform, line.xMpt(), line.baselineYMpt())
                            / 1000.0 / page.userUnit()),
                    (float) (applyY(transform, line.xMpt(), line.baselineYMpt())
                            / 1000.0 / page.userUnit()));
            canvas.showText(line.text());
            canvas.endText();
            canvas.endMarkedContentSequence();
            canvas.restoreState();
        }
    }

    private static byte[] createContinuation(ContractSupport.Job job, Path fontPath)
            throws IOException, DocumentException {
        if (job.answers().stream().noneMatch(answer -> answer.classification().equals("appendix"))) {
            return new byte[0];
        }
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        Document document = new Document(PageSize.LETTER, 54, 54, 64, 54);
        document.setGlyphSubstitutionEnabled(false);
        PdfWriter writer = PdfWriter.getInstance(document, output);
        BaseFont baseFont = BaseFont.createFont(
                fontPath.toString(), BaseFont.IDENTITY_H, BaseFont.EMBEDDED);
        writer.setPageEvent(new PageNumberEvent(baseFont));
        Font eyebrow = new Font(baseFont, 10, Font.BOLD, new Color(29, 78, 216));
        Font heading = new Font(baseFont, 16, Font.BOLD, new Color(17, 24, 39));
        Font label = new Font(baseFont, 10, Font.BOLD, new Color(51, 65, 85));
        Font body = new Font(baseFont, 11, Font.NORMAL, new Color(17, 24, 39));
        document.open();
        boolean first = true;
        for (ContractSupport.Answer answer : job.answers()) {
            if (!answer.classification().equals("appendix")) {
                continue;
            }
            if (!first) {
                document.newPage();
            }
            first = false;
            ContractSupport.Continuation continuation = answer.continuation();
            add(document, "CLAROS ATTACHED ANSWER PAGE", eyebrow, 8);
            add(document, continuation.worksheetTitle(), label, 3);
            add(document, "Source page " + continuation.sourcePageNumber(), label, 12);
            add(document, answer.displayIdentifier(), heading, 14);
            add(document, "Exact source question", label, 4);
            add(document, continuation.sourceQuestion(), body, 18);
            add(document, "Exact approved answer", label, 6);
            for (String paragraphText : continuation.paragraphs()) {
                Paragraph paragraph = new Paragraph(paragraphText, body);
                paragraph.setLeading(15);
                paragraph.setSpacingAfter(12);
                document.add(paragraph);
            }
        }
        document.close();
        return output.toByteArray();
    }

    private static void add(Document document, String text, Font font, float spacing)
            throws DocumentException {
        Paragraph paragraph = new Paragraph(text, font);
        paragraph.setLeading(font.getSize() + 4);
        paragraph.setSpacingAfter(spacing);
        document.add(paragraph);
    }

    private static int appendContinuation(PdfStamper stamper, int sourcePages, byte[] payload)
            throws IOException {
        if (payload.length == 0) {
            return 0;
        }
        try (PdfReader continuation = new PdfReader(payload)) {
            for (int page = 1; page <= continuation.getNumberOfPages(); page++) {
                Rectangle sourceSize = continuation.getPageSize(page);
                Rectangle insertedSize = new Rectangle(sourceSize);
                insertedSize.setRotation(continuation.getPageRotation(page));
                int outputPage = sourcePages + page;
                stamper.insertPage(outputPage, insertedSize);
                PdfImportedPage imported = stamper.getImportedPage(continuation, page);
                stamper.getOverContent(outputPage).addTemplate(imported, 0, 0);
            }
            return continuation.getNumberOfPages();
        }
    }

    private static void verifyGeometry(PdfReader reader, java.util.List<ContractSupport.PageGeometry> pages)
            throws WorkerRejection {
        for (ContractSupport.PageGeometry expected : pages) {
            int page = expected.pageNumber();
            PdfNumber rawUserUnit = reader.getPageN(page).getAsNumber(PdfName.USERUNIT);
            double userUnit = rawUserUnit == null ? 1 : rawUserUnit.doubleValue();
            if (Math.abs(userUnit - expected.userUnit()) > 0.000_001
                    || Math.floorMod(reader.getPageRotation(page), 360) != expected.rotation()
                    || !sameBox(reader.getPageSize(page), expected.mediaBoxMpt(), userUnit)
                    || !sameBox(reader.getCropBox(page), expected.cropBoxMpt(), userUnit)) {
                throw new WorkerRejection("stale_physical_ir");
            }
        }
    }

    private static boolean sameBox(Rectangle actual, int[] expected, double userUnit) {
        double[] values = {actual.getLeft(), actual.getBottom(), actual.getRight(), actual.getTop()};
        for (int index = 0; index < values.length; index++) {
            if (Math.abs(values[index] * userUnit * 1000 - expected[index]) > 1.1) {
                return false;
            }
        }
        return true;
    }

    private static void verifyGlyphs(ContractSupport.Job job, BaseFont font) throws WorkerRejection {
        for (ContractSupport.Answer answer : job.answers()) {
            for (int codePoint : answer.committedText().codePoints().toArray()) {
                if (codePoint != '\n' && codePoint != '\r' && !font.charExists(codePoint)) {
                    throw new WorkerRejection("unsupported_glyph");
                }
            }
            if (answer.continuation() != null) {
                for (String value : new String[]{answer.displayIdentifier(),
                        answer.continuation().worksheetTitle(), answer.continuation().sourceQuestion()}) {
                    for (int codePoint : value.codePoints().toArray()) {
                        if (!font.charExists(codePoint)) {
                            throw new WorkerRejection("unsupported_glyph");
                        }
                    }
                }
            }
        }
    }

    private static int applyX(int[] matrix, int x, int y) {
        return matrix[0] * x + matrix[2] * y + matrix[4];
    }

    private static int applyY(int[] matrix, int x, int y) {
        return matrix[1] * x + matrix[3] * y + matrix[5];
    }

    private static Path requireFile(Path path) throws WorkerRejection {
        Path resolved = path.toAbsolutePath().normalize();
        if (!Files.isRegularFile(resolved) || Files.isSymbolicLink(resolved)) {
            throw new WorkerRejection("invalid_contract");
        }
        return resolved;
    }

    private static void requireDirectory(Path path) throws WorkerRejection {
        if (!Files.isDirectory(path) || Files.isSymbolicLink(path)) {
            throw new WorkerRejection("invalid_contract");
        }
    }

    private static void writeFailure(Path jobRoot, String rawCode) {
        try {
            String code = SAFE_CODES.contains(rawCode) ? rawCode : "internal_error";
            ObjectNode status = ContractSupport.MAPPER.createObjectNode();
            status.put("schema_version", 1);
            status.put("status", "error");
            status.put("code", code);
            writeStatus(jobRoot, status);
        } catch (Exception ignored) {
            // The parent treats a missing/malformed status as a closed failure.
        }
    }

    private static void writeStatus(Path root, ObjectNode status) throws IOException {
        Path temporary = root.resolve("worker-status.tmp");
        Files.write(temporary, ContractSupport.MAPPER.writeValueAsBytes(status));
        moveAtomically(temporary, root.resolve("worker-status.json"));
    }

    private static void moveAtomically(Path source, Path target) throws IOException {
        try {
            Files.move(source, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
        } catch (AtomicMoveNotSupportedException error) {
            Files.move(source, target, StandardCopyOption.REPLACE_EXISTING);
        }
    }

    private record Arguments(Path jobRoot, Path fontRoot) {
        static Arguments parse(String[] args) throws WorkerRejection {
            if (args.length != 4 || !"--job-dir".equals(args[0]) || !"--font-dir".equals(args[2])) {
                throw new WorkerRejection("invalid_contract");
            }
            return new Arguments(
                    Path.of(args[1]).toAbsolutePath().normalize(),
                    Path.of(args[3]).toAbsolutePath().normalize());
        }
    }

    private static final class WorkerRejection extends Exception {
        private final String code;

        WorkerRejection(String code) {
            super(code);
            this.code = code;
        }

        String code() {
            return code;
        }
    }

    private static final class BoundedOutputStream extends OutputStream {
        private final OutputStream delegate;
        private final long maximum;
        private long count;
        private final boolean[] exceeded;

        private BoundedOutputStream(OutputStream delegate, long maximum, boolean[] exceeded) {
            this.delegate = delegate;
            this.maximum = maximum;
            this.exceeded = exceeded;
        }

        @Override
        public void write(int value) throws IOException {
            reserve(1);
            delegate.write(value);
        }

        @Override
        public void write(byte[] bytes, int offset, int length) throws IOException {
            reserve(length);
            delegate.write(bytes, offset, length);
        }

        private void reserve(int amount) throws BoundExceededException {
            if (amount < 0 || count + amount > maximum) {
                exceeded[0] = true;
                throw new BoundExceededException();
            }
            count += amount;
        }

        @Override
        public void flush() throws IOException {
            delegate.flush();
        }

        @Override
        public void close() throws IOException {
            delegate.close();
        }
    }

    private static final class BoundExceededException extends IOException {
    }

    private static final class PageNumberEvent extends PdfPageEventHelper {
        private final BaseFont font;

        private PageNumberEvent(BaseFont font) {
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
                    document.right(), 32, 0);
            canvas.endText();
            canvas.restoreState();
        }
    }
}
