package org.claros.openpdfhostile;

public record PhysicalPlacement(
        String id,
        int pageNumber,
        double xPt,
        double baselineFromTopPt,
        double fontSizePt,
        double maskWidthPt,
        double maskHeightPt,
        String text,
        FontKind font,
        boolean rtl) {
}

