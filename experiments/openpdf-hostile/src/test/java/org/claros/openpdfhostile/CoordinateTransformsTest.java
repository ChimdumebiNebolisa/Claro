package org.claros.openpdfhostile;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CoordinateTransformsTest {
    @Test
    void physicalPointsRoundTripForEveryRotationWithCropOffsetAndUserUnit() {
        for (int rotation : new int[]{0, 90, 180, 270}) {
            CoordinateTransforms.PageGeometry page = new CoordinateTransforms.PageGeometry(
                    36, 54, 540, 684, rotation, 2);
            double x = page.displayedWidthPt() * 0.31;
            double y = page.displayedHeightPt() * 0.67;
            CoordinateTransforms.PdfPoint pdf = CoordinateTransforms.physicalToPdf(page, x, y);
            CoordinateTransforms.PhysicalPoint roundTrip = CoordinateTransforms.pdfToPhysical(
                    page, pdf.x(), pdf.y());
            assertEquals(x, roundTrip.xPt(), 0.000_001, "x at rotation " + rotation);
            assertEquals(y, roundTrip.yFromTopPt(), 0.000_001, "y at rotation " + rotation);
        }
    }

    @Test
    void uprightTextBasisMatchesPhysicalDisplayAxes() {
        for (int rotation : new int[]{0, 90, 180, 270}) {
            CoordinateTransforms.PageGeometry page = new CoordinateTransforms.PageGeometry(
                    -10, 20, 612, 792, rotation, 1);
            CoordinateTransforms.TextMatrix matrix = CoordinateTransforms.uprightTextMatrix(page, 100, 200);
            CoordinateTransforms.PhysicalPoint origin = CoordinateTransforms.pdfToPhysical(page, matrix.e(), matrix.f());
            CoordinateTransforms.PhysicalPoint textRight = CoordinateTransforms.pdfToPhysical(
                    page, matrix.e() + matrix.a(), matrix.f() + matrix.b());
            CoordinateTransforms.PhysicalPoint textUp = CoordinateTransforms.pdfToPhysical(
                    page, matrix.e() + matrix.c(), matrix.f() + matrix.d());
            assertEquals(100, origin.xPt(), 0.000_001);
            assertEquals(200, origin.yFromTopPt(), 0.000_001);
            assertEquals(1, textRight.xPt() - origin.xPt(), 0.000_001);
            assertEquals(0, textRight.yFromTopPt() - origin.yFromTopPt(), 0.000_001);
            assertEquals(0, textUp.xPt() - origin.xPt(), 0.000_001);
            assertEquals(-1, textUp.yFromTopPt() - origin.yFromTopPt(), 0.000_001);
        }
    }
}

