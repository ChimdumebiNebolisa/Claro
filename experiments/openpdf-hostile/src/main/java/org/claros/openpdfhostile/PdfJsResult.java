package org.claros.openpdfhostile;

public record PdfJsResult(
        String fixture,
        Status status,
        int pageCount,
        int renderedPages,
        boolean overlayTextPresent,
        String extractedOverlayText,
        String detail) {
}
