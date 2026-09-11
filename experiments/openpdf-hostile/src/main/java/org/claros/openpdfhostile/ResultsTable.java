package org.claros.openpdfhostile;

import java.util.StringJoiner;

public final class ResultsTable {
    private ResultsTable() {
    }

    public static String render(HarnessEvidence evidence) {
        StringBuilder output = new StringBuilder();
        output.append("| Fixture | Open/read | Preserves source | Overlay succeeds | Coordinate correct | Unicode correct | Continuation works | qpdf validation | PDF.js reopen/render | Source losses | Verdict |\n");
        output.append("|---|---|---|---|---|---|---|---|---|---|---|\n");
        for (CaseResult result : evidence.cases()) {
            StringJoiner losses = new StringJoiner("; ");
            result.knownLosses().forEach(losses::add);
            output.append("| ").append(escape(result.fixture()))
                    .append(" | ").append(result.openRead())
                    .append(" | ").append(result.preservesSource())
                    .append(" | ").append(result.overlaySucceeds())
                    .append(" | ").append(result.coordinateCorrect())
                    .append(" | ").append(result.unicodeCorrect())
                    .append(" | ").append(result.continuationWorks())
                    .append(" | ").append(result.qpdfValidation())
                    .append(" | ").append(result.pdfjsRender())
                    .append(" | ").append(escape(losses.length() == 0 ? "None observed" : losses.toString()))
                    .append(" | ").append(result.verdict()).append(" |\n");
        }
        return output.toString();
    }

    private static String escape(String value) {
        return value.replace("|", "\\|").replace("\n", " ");
    }
}
