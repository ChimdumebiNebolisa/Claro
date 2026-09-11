package org.claros.openpdfhostile;

import java.util.List;
import java.util.Map;

public record HarnessEvidence(
        String schemaVersion,
        String generatedAt,
        String gitHead,
        String gitBranch,
        String openPdfVersion,
        String pdfBoxVersion,
        String javaVersion,
        String operatingSystem,
        String qpdfVersion,
        Map<String, String> commands,
        List<CaseResult> cases) {

    public HarnessEvidence {
        commands = Map.copyOf(commands);
        cases = List.copyOf(cases);
    }

    public HarnessEvidence withCases(List<CaseResult> updatedCases) {
        return new HarnessEvidence(
                schemaVersion,
                generatedAt,
                gitHead,
                gitBranch,
                openPdfVersion,
                pdfBoxVersion,
                javaVersion,
                operatingSystem,
                qpdfVersion,
                commands,
                updatedCases);
    }
}

