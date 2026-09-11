package org.claros.openpdfhostile;

import org.apache.pdfbox.Loader;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.openpdf.text.Document;
import org.openpdf.text.pdf.PdfReader;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

public final class HarnessEvaluator {
    private final Path experimentRoot;
    private final Path targetRoot;
    private final Map<FontKind, Path> fonts;
    private final Path qpdf;

    public HarnessEvaluator(Path experimentRoot, Path targetRoot, Map<FontKind, Path> fonts) {
        this.experimentRoot = experimentRoot;
        this.targetRoot = targetRoot;
        this.fonts = fonts;
        this.qpdf = locateQpdf(experimentRoot);
    }

    public HarnessEvidence run(List<CorpusGenerator.GeneratedFixture> fixtures) throws IOException {
        Path derivatives = targetRoot.resolve("derivatives");
        Files.createDirectories(derivatives);
        OpenPdfSpike spike = new OpenPdfSpike(fonts);
        IndependentValidator validator = new IndependentValidator();
        List<CaseResult> results = new ArrayList<>();
        for (CorpusGenerator.GeneratedFixture fixture : fixtures) {
            results.add(evaluateOne(spike, validator, fixture, derivatives));
        }
        Map<String, String> commands = new LinkedHashMap<>();
        commands.put("unit_and_integration_tests", "mvn test");
        commands.put("corpus_and_openpdf", "mvn exec:java -Dexec.args=run");
        commands.put("pdfjs", "node scripts/validate-pdfjs.mjs target/evidence/pdfjs-cases.json target/evidence/pdfjs-results.json");
        commands.put("report", "mvn exec:java -Dexec.args=report");
        return new HarnessEvidence(
                "claros-openpdf-hostile-evidence-v1",
                Instant.now().toString(),
                git("rev-parse", "HEAD"),
                git("branch", "--show-current"),
                Document.getRelease(),
                org.apache.pdfbox.util.Version.getVersion(),
                System.getProperty("java.version"),
                System.getProperty("os.name") + " " + System.getProperty("os.version")
                        + " " + System.getProperty("os.arch"),
                qpdf == null ? "UNAVAILABLE" : processVersion(qpdf),
                commands,
                results);
    }

    private CaseResult evaluateOne(
            OpenPdfSpike spike,
            IndependentValidator validator,
            CorpusGenerator.GeneratedFixture fixture,
            Path derivatives) throws IOException {
        FixtureSpec spec = fixture.spec();
        Path derivative = derivatives.resolve(spec.id() + "-openpdf.pdf");
        Files.deleteIfExists(derivative);
        String sourceBefore = FontAssets.digest(fixture.path());
        OpenPdfSpike.OpenReadResult read = spike.probeOpen(spec, fixture.path());
        List<String> evidence = new ArrayList<>();
        List<String> losses = new ArrayList<>();
        if (read.error() != null) {
            evidence.add("OpenPDF source read: " + read.error());
        } else {
            evidence.add("OpenPDF source read: " + read.pageCount() + " page(s), rebuiltXref="
                    + read.readerRebuilt());
        }
        QpdfResult sourceQpdf = qpdfCheck(fixture.path(), spec.userPassword());
        if (sourceQpdf.detail() != null) {
            evidence.add("qpdf source check: " + sourceQpdf.detail());
        }
        if (!read.opened()) {
            String sourceAfter = FontAssets.digest(fixture.path());
            losses.add("OpenPDF could not open the source");
            return failedWithoutDerivative(
                    fixture, sourceBefore, sourceAfter, Status.FAIL, losses, evidence, read.readerRebuilt());
        }

        try {
            OpenPdfSpike.OpenResult openResult = spike.process(spec, fixture.path(), derivative);
            evidence.add("OpenPDF stamping mode: "
                    + (openResult.incrementalAppend()
                    ? "incremental append"
                    : "full rewrite after rebuilt xref"));
            String sourceAfter = FontAssets.digest(fixture.path());
            if (!sourceBefore.equals(sourceAfter)) {
                losses.add("immutable source bytes changed");
            }
            OpenPdfSpike.OpenReadResult derivativeRead = spike.probeOpen(spec, derivative);
            Status openRead = derivativeRead.opened() ? Status.PASS : Status.FAIL;
            evidence.add("OpenPDF derivative reopen: "
                    + (derivativeRead.opened() ? derivativeRead.pageCount() + " page(s)" : derivativeRead.error()));
            IndependentValidator.ValidationResult validated = validator.validate(spec, fixture.path(), openResult);
            losses.addAll(validated.knownLosses());
            for (String id : validated.missingOverlayText()) {
                evidence.add("missing exact extracted overlay text: " + id);
            }
            evidence.addAll(validated.coordinateDetails());
            evidence.addAll(validated.continuationDetails());
            evidence.add("render comparison outside overlay masks: "
                    + validated.outsideMaskPixelDifferences() + " differing pixel(s) at 96 DPI");

            QpdfResult derivativeQpdf = qpdfCheck(derivative, spec.userPassword());
            if (derivativeQpdf.detail() != null) {
                evidence.add("qpdf derivative check: " + derivativeQpdf.detail());
            }
            Status preservation = validated.preservesSource() && sourceBefore.equals(sourceAfter)
                    ? Status.PASS : Status.FAIL;
            Status overlay = validated.overlayTextPresent() ? Status.PASS : Status.FAIL;
            Status coordinate = validated.coordinateCorrect() ? Status.PASS : Status.FAIL;
            Status unicode = unicodeStatus(spec, validated.overlayTextPresent(), evidence);
            Status continuation = validated.continuationStatus();
            Status pdfJs = Status.NOT_APPLICABLE;
            Status verdict = CaseResult.aggregateVerdict(
                    preservation,
                    overlay,
                    coordinate,
                    unicode,
                    continuation,
                    derivativeQpdf.status());
            return new CaseResult(
                    spec.id(),
                    spec.description(),
                    relativize(fixture.path()),
                    relativize(derivative),
                    sourceBefore,
                    sourceAfter,
                    openResult.derivativeSha256(),
                    openRead,
                    preservation,
                    overlay,
                    coordinate,
                    unicode,
                    continuation,
                    derivativeQpdf.status(),
                    pdfJs,
                    verdict,
                    openResult.readerRebuilt(),
                    read.pageCount(),
                    derivativeRead.pageCount(),
                    openResult.continuationPages(),
                    validated.outsideMaskPixelDifferences(),
                    losses,
                    evidence,
                    validated.sourceSnapshot(),
                    validated.outputSnapshot());
        } catch (Exception error) {
            String sourceAfter = FontAssets.digest(fixture.path());
            String message = describe(error);
            evidence.add("OpenPDF derivative creation: " + message);
            losses.add(error instanceof OpenPdfSpike.UnsupportedGlyphException
                    ? "overlay rejected safely because the selected font/engine could not map every glyph"
                    : "OpenPDF did not produce a validated derivative");
            Status unicode = spec.unicodeCase() ? Status.FAIL : Status.NOT_APPLICABLE;
            return failedWithoutDerivative(
                    fixture,
                    sourceBefore,
                    sourceAfter,
                    unicode,
                    losses,
                    evidence,
                    read.readerRebuilt());
        }
    }

    private CaseResult failedWithoutDerivative(
            CorpusGenerator.GeneratedFixture fixture,
            String sourceBefore,
            String sourceAfter,
            Status unicode,
            List<String> losses,
            List<String> evidence,
            boolean readerRebuilt) {
        FixtureSpec spec = fixture.spec();
        return new CaseResult(
                spec.id(),
                spec.description(),
                relativize(fixture.path()),
                "",
                sourceBefore,
                sourceAfter,
                "",
                Status.PASS,
                Status.NOT_APPLICABLE,
                Status.FAIL,
                Status.NOT_APPLICABLE,
                unicode,
                spec.continuation() ? Status.FAIL : Status.NOT_APPLICABLE,
                Status.NOT_APPLICABLE,
                Status.NOT_APPLICABLE,
                Status.FAIL,
                readerRebuilt,
                0,
                0,
                0,
                0,
                losses,
                evidence,
                null,
                null);
    }

    private static Status unicodeStatus(
            FixtureSpec spec,
            boolean exactExtracted,
            List<String> evidence) {
        if (!spec.unicodeCase()) {
            return Status.NOT_APPLICABLE;
        }
        if (!exactExtracted) {
            return Status.FAIL;
        }
        if (spec.id().endsWith("-rtl")) {
            evidence.add("RTL logical extraction and render completed; glyph shaping order is not machine-proven");
            return Status.PARTIAL;
        }
        return Status.PASS;
    }

    private QpdfResult qpdfCheck(Path pdf, String password) {
        if (qpdf == null || !Files.isRegularFile(pdf)) {
            return new QpdfResult(Status.NOT_APPLICABLE, "qpdf executable unavailable");
        }
        List<String> command = new ArrayList<>();
        command.add(qpdf.toString());
        if (password != null) {
            command.add("--password=" + password);
        }
        command.add("--check");
        command.add(pdf.toString());
        try {
            Process process = new ProcessBuilder(command)
                    .redirectErrorStream(true)
                    .start();
            boolean completed = process.waitFor(60, TimeUnit.SECONDS);
            if (!completed) {
                process.destroyForcibly();
                return new QpdfResult(Status.FAIL, "timed out after 60 seconds");
            }
            String output = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8).strip();
            Status status = process.exitValue() == 0
                    ? Status.PASS
                    : process.exitValue() == 3 ? Status.PARTIAL : Status.FAIL;
            return new QpdfResult(status, "exit " + process.exitValue()
                    + (output.isEmpty() ? "" : ": " + singleLine(output)));
        } catch (IOException | InterruptedException error) {
            if (error instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }
            return new QpdfResult(Status.FAIL, describe(error));
        }
    }

    private String relativize(Path path) {
        return experimentRoot.relativize(path.toAbsolutePath().normalize()).toString().replace('\\', '/');
    }

    private static Path locateQpdf(Path experimentRoot) {
        String configured = System.getenv("OPENPDF_QPDF");
        if (configured != null && Files.isRegularFile(Path.of(configured))) {
            return Path.of(configured).toAbsolutePath();
        }
        Path local = experimentRoot.resolve(".tools/qpdf/bin/qpdf.exe");
        if (Files.isRegularFile(local)) {
            return local.toAbsolutePath();
        }
        try {
            Process process = new ProcessBuilder("where.exe", "qpdf").start();
            if (process.waitFor(5, TimeUnit.SECONDS) && process.exitValue() == 0) {
                String first = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8)
                        .lines().findFirst().orElse("").strip();
                if (!first.isEmpty() && Files.isRegularFile(Path.of(first))) {
                    return Path.of(first).toAbsolutePath();
                }
            }
        } catch (IOException | InterruptedException ignored) {
            Thread.currentThread().interrupt();
        }
        return null;
    }

    private static String processVersion(Path executable) {
        try {
            Process process = new ProcessBuilder(executable.toString(), "--version")
                    .redirectErrorStream(true)
                    .start();
            if (!process.waitFor(10, TimeUnit.SECONDS)) {
                process.destroyForcibly();
                return "UNKNOWN";
            }
            return singleLine(new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8));
        } catch (IOException | InterruptedException error) {
            if (error instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }
            return "UNKNOWN";
        }
    }

    private String git(String... arguments) {
        List<String> command = new ArrayList<>();
        command.add("git");
        command.addAll(List.of(arguments));
        try {
            Process process = new ProcessBuilder(command)
                    .directory(experimentRoot.toFile())
                    .redirectErrorStream(true)
                    .start();
            if (!process.waitFor(10, TimeUnit.SECONDS) || process.exitValue() != 0) {
                return "unknown";
            }
            return new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8).strip();
        } catch (IOException | InterruptedException error) {
            if (error instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }
            return "unknown";
        }
    }

    private static String singleLine(String value) {
        return value.replace('\r', ' ').replace('\n', ' ').replaceAll("\\s+", " ").strip();
    }

    private static String describe(Throwable error) {
        Throwable current = error;
        while (current.getCause() != null && current.getCause() != current) {
            current = current.getCause();
        }
        String message = current.getMessage();
        return current.getClass().getSimpleName() + (message == null ? "" : ": " + message);
    }

    private record QpdfResult(Status status, String detail) {
    }
}
