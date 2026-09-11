package org.claros.openpdfhostile;

public final class CoordinateTransforms {
    private CoordinateTransforms() {
    }

    public record PageGeometry(
            double cropLlx,
            double cropLly,
            double cropWidthUser,
            double cropHeightUser,
            int rotation,
            double userUnit) {

        public PageGeometry {
            rotation = Math.floorMod(rotation, 360);
            if (rotation % 90 != 0 || userUnit <= 0) {
                throw new IllegalArgumentException("Rotation and UserUnit must define a valid PDF page");
            }
        }

        public double displayedWidthPt() {
            return (rotation == 90 || rotation == 270 ? cropHeightUser : cropWidthUser) * userUnit;
        }

        public double displayedHeightPt() {
            return (rotation == 90 || rotation == 270 ? cropWidthUser : cropHeightUser) * userUnit;
        }
    }

    public record PdfPoint(double x, double y) {
    }

    public record PhysicalPoint(double xPt, double yFromTopPt) {
    }

    public record TextMatrix(double a, double b, double c, double d, double e, double f) {
    }

    public static PdfPoint physicalToPdf(PageGeometry page, double xPt, double yFromTopPt) {
        double x = xPt / page.userUnit();
        double y = yFromTopPt / page.userUnit();
        return switch (page.rotation()) {
            case 0 -> new PdfPoint(page.cropLlx() + x,
                    page.cropLly() + page.cropHeightUser() - y);
            case 90 -> new PdfPoint(page.cropLlx() + y, page.cropLly() + x);
            case 180 -> new PdfPoint(page.cropLlx() + page.cropWidthUser() - x,
                    page.cropLly() + y);
            case 270 -> new PdfPoint(page.cropLlx() + page.cropWidthUser() - y,
                    page.cropLly() + page.cropHeightUser() - x);
            default -> throw new IllegalArgumentException("Unsupported rotation");
        };
    }

    public static PhysicalPoint pdfToPhysical(PageGeometry page, double pdfX, double pdfY) {
        double u = pdfX - page.cropLlx();
        double v = pdfY - page.cropLly();
        double x;
        double y;
        switch (page.rotation()) {
            case 0 -> {
                x = u;
                y = page.cropHeightUser() - v;
            }
            case 90 -> {
                x = v;
                y = u;
            }
            case 180 -> {
                x = page.cropWidthUser() - u;
                y = v;
            }
            case 270 -> {
                x = page.cropHeightUser() - v;
                y = page.cropWidthUser() - u;
            }
            default -> throw new IllegalArgumentException("Unsupported rotation");
        }
        return new PhysicalPoint(x * page.userUnit(), y * page.userUnit());
    }

    public static TextMatrix uprightTextMatrix(
            PageGeometry page,
            double xPt,
            double baselineFromTopPt) {
        PdfPoint anchor = physicalToPdf(page, xPt, baselineFromTopPt);
        return switch (page.rotation()) {
            case 0 -> new TextMatrix(1, 0, 0, 1, anchor.x(), anchor.y());
            case 90 -> new TextMatrix(0, 1, -1, 0, anchor.x(), anchor.y());
            case 180 -> new TextMatrix(-1, 0, 0, -1, anchor.x(), anchor.y());
            case 270 -> new TextMatrix(0, -1, 1, 0, anchor.x(), anchor.y());
            default -> throw new IllegalArgumentException("Unsupported rotation");
        };
    }
}

