package org.claros.openpdfhostile;

import java.util.List;

public record CaseResult(
        String fixture,
        String description,
        String sourcePath,
        String derivativePath,
        String sourceSha256Before,
        String sourceSha256After,
        String derivativeSha256,
        Status openRead,
        Status preservesSource,
        Status overlaySucceeds,
        Status coordinateCorrect,
        Status unicodeCorrect,
        Status continuationWorks,
        Status qpdfValidation,
        Status pdfjsRender,
        Status verdict,
        boolean openPdfRebuiltSourceXref,
        int sourcePageCount,
        int derivativePageCount,
        int continuationPageCount,
        long outsideMaskPixelDifferences,
        List<String> knownLosses,
        List<String> evidence,
        IndependentValidator.Snapshot sourceSnapshot,
        IndependentValidator.Snapshot outputSnapshot) {

    public CaseResult {
        knownLosses = List.copyOf(knownLosses);
        evidence = List.copyOf(evidence);
    }

    public CaseResult withPdfJs(Status status, String detail) {
        List<String> updatedEvidence = new java.util.ArrayList<>(evidence);
        if (detail != null && !detail.isBlank()) {
            updatedEvidence.add("PDF.js: " + detail);
        }
        return new CaseResult(
                fixture,
                description,
                sourcePath,
                derivativePath,
                sourceSha256Before,
                sourceSha256After,
                derivativeSha256,
                openRead,
                preservesSource,
                overlaySucceeds,
                coordinateCorrect,
                unicodeCorrect,
                continuationWorks,
                qpdfValidation,
                status,
                aggregateVerdict(
                        preservesSource,
                        overlaySucceeds,
                        coordinateCorrect,
                        unicodeCorrect,
                        continuationWorks,
                        qpdfValidation,
                        status),
                openPdfRebuiltSourceXref,
                sourcePageCount,
                derivativePageCount,
                continuationPageCount,
                outsideMaskPixelDifferences,
                knownLosses,
                updatedEvidence,
                sourceSnapshot,
                outputSnapshot);
    }

    public static Status aggregateVerdict(Status... statuses) {
        boolean partial = false;
        for (Status status : statuses) {
            if (status == Status.FAIL) {
                return Status.FAIL;
            }
            if (status == Status.PARTIAL) {
                partial = true;
            }
        }
        return partial ? Status.PARTIAL : Status.PASS;
    }
}

