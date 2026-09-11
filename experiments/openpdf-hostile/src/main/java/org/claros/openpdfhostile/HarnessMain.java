package org.claros.openpdfhostile;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class HarnessMain {
    private static final ObjectMapper JSON = new ObjectMapper()
            .enable(SerializationFeature.INDENT_OUTPUT);

    private HarnessMain() {
    }

    public static void main(String[] args) throws Exception {
        Path experimentRoot = Path.of("").toAbsolutePath().normalize();
        Path targetRoot = experimentRoot.resolve("target");
        String command = args.length == 0 ? "run" : args[0];
        switch (command) {
            case "generate" -> generate(experimentRoot, targetRoot);
            case "run" -> run(experimentRoot, targetRoot);
            case "report" -> report(targetRoot);
            case "office-investigation" -> {
                OfficeExtractionInvestigation.InvestigationResult result =
                        OfficeExtractionInvestigation.run(experimentRoot, targetRoot);
                System.out.println("Wrote " + result.cases().size()
                        + " office extraction cases to "
                        + targetRoot.resolve("office-investigation/pdfbox-structure-results.json"));
            }
            default -> throw new IllegalArgumentException(
                    "Expected generate, run, report, or office-investigation");
        }
    }

    private static List<CorpusGenerator.GeneratedFixture> generate(
            Path experimentRoot,
            Path targetRoot) throws Exception {
        Map<FontKind, Path> fonts = FontAssets.prepare(experimentRoot, targetRoot);
        CorpusGenerator generator = new CorpusGenerator(targetRoot.resolve("fixtures"), fonts);
        List<CorpusGenerator.GeneratedFixture> fixtures = generator.generateAll();
        Files.createDirectories(targetRoot.resolve("evidence"));
        JSON.writeValue(targetRoot.resolve("evidence/fixture-manifest.json").toFile(), fixtures);
        return fixtures;
    }

    private static void run(Path experimentRoot, Path targetRoot) throws Exception {
        List<CorpusGenerator.GeneratedFixture> fixtures = generate(experimentRoot, targetRoot);
        Map<FontKind, Path> fonts = FontAssets.prepare(experimentRoot, targetRoot);
        HarnessEvidence evidence = new HarnessEvaluator(experimentRoot, targetRoot, fonts).run(fixtures);
        Path evidenceDirectory = targetRoot.resolve("evidence");
        JSON.writeValue(evidenceDirectory.resolve("base-results.json").toFile(), evidence);
        List<Map<String, Object>> pdfJsCases = new ArrayList<>();
        for (CaseResult result : evidence.cases()) {
            if (result.derivativePath().isBlank()) {
                continue;
            }
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("fixture", result.fixture());
            item.put("path", experimentRoot.resolve(result.derivativePath()).toString());
            FixtureSpec spec = CorpusPlan.fixtures().stream()
                    .filter(candidate -> candidate.id().equals(result.fixture()))
                    .findFirst().orElseThrow();
            item.put("password", spec.encrypted() ? spec.userPassword() : "");
            item.put("expectedPages", result.derivativePageCount());
            item.put("overlayPage", spec.overlayPage());
            item.put("expectedOverlayTexts", spec.anchors().stream()
                    .map(anchor -> spec.anchors().size() == 1
                            ? spec.overlayText()
                            : spec.overlayText() + " [" + anchor.name() + "]")
                    .toList());
            pdfJsCases.add(item);
        }
        JSON.writeValue(evidenceDirectory.resolve("pdfjs-cases.json").toFile(), pdfJsCases);
        System.out.println("Wrote " + evidence.cases().size() + " base case results to "
                + evidenceDirectory.resolve("base-results.json"));
    }

    private static void report(Path targetRoot) throws IOException {
        Path evidenceDirectory = targetRoot.resolve("evidence");
        HarnessEvidence evidence = JSON.readValue(
                evidenceDirectory.resolve("base-results.json").toFile(),
                HarnessEvidence.class);
        Map<String, PdfJsResult> pdfJsByFixture = new LinkedHashMap<>();
        Path pdfJsPath = evidenceDirectory.resolve("pdfjs-results.json");
        if (Files.isRegularFile(pdfJsPath)) {
            List<PdfJsResult> results = JSON.readValue(
                    pdfJsPath.toFile(),
                    new TypeReference<>() {});
            for (PdfJsResult result : results) {
                pdfJsByFixture.put(result.fixture(), result);
            }
        }
        List<CaseResult> merged = new ArrayList<>();
        for (CaseResult result : evidence.cases()) {
            PdfJsResult pdfJs = pdfJsByFixture.get(result.fixture());
            if (result.derivativePath().isBlank()) {
                merged.add(result);
            } else if (pdfJs == null) {
                merged.add(result.withPdfJs(Status.NOT_APPLICABLE, "validator result unavailable"));
            } else {
                merged.add(result.withPdfJs(pdfJs.status(), pdfJs.detail()));
            }
        }
        HarnessEvidence finalEvidence = evidence.withCases(merged);
        JSON.writeValue(evidenceDirectory.resolve("results.json").toFile(), finalEvidence);
        Path markdown = evidenceDirectory.resolve("results-table.md");
        Files.writeString(markdown, ResultsTable.render(finalEvidence));
        System.out.println("Wrote merged evidence to " + evidenceDirectory.resolve("results.json"));
        System.out.println("Wrote result table to " + markdown);
    }
}
