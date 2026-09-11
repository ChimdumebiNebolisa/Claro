package org.claros.openpdfhostile;

import org.apache.pdfbox.Loader;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class EndToEndSmokeTest {
    @TempDir
    Path temporary;

    @Test
    void representativeSourcesAreStampedReopenedAndIndependentlyValidated() throws Exception {
        Path experimentRoot = Path.of("").toAbsolutePath().normalize();
        Map<FontKind, Path> fonts = FontAssets.prepare(experimentRoot, temporary);
        CorpusGenerator generator = new CorpusGenerator(temporary.resolve("fixtures"), fonts);
        var fixtures = generator.generateAll();
        Set<String> representative = Set.of(
                "normal-letter", "rotated-90", "cropbox-offset", "acroform",
                "unicode-text", "long-multiline-answer", "encrypted", "outlines",
                "metadata", "user-unit-2");
        OpenPdfSpike spike = new OpenPdfSpike(fonts);
        IndependentValidator validator = new IndependentValidator();

        for (var fixture : fixtures) {
            if (!representative.contains(fixture.spec().id())) {
                continue;
            }
            Path derivative = temporary.resolve("derivatives/" + fixture.spec().id() + ".pdf");
            String sourceBefore = FontAssets.digest(fixture.path());
            OpenPdfSpike.OpenResult result = spike.process(fixture.spec(), fixture.path(), derivative);
            assertEquals(sourceBefore, FontAssets.digest(fixture.path()), fixture.spec().id());
            assertTrue(result.derivativeSha256().length() == 64);
            IndependentValidator.ValidationResult validation = validator.validate(
                    fixture.spec(), fixture.path(), result);
            assertTrue(validation.overlayTextPresent(), fixture.spec().id() + validation.missingOverlayText());
            assertTrue(validation.coordinateCorrect(), fixture.spec().id() + validation.coordinateDetails());
            assertFalse(validation.knownLosses().contains("source page dimensions, rotation, UserUnit, or page boxes changed"));
            String password = fixture.spec().encrypted() ? fixture.spec().userPassword() : "";
            try (var reopened = Loader.loadPDF(derivative.toFile(), password)) {
                assertTrue(reopened.getNumberOfPages() >= 1);
            }
        }
    }
}
