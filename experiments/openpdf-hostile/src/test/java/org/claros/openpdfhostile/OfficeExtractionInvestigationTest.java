package org.claros.openpdfhostile;

import org.openpdf.text.pdf.BaseFont;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OfficeExtractionInvestigationTest {
    @TempDir
    Path temporary;

    @Test
    void sourceTextIsPreservedAndDisablingGlyphSubstitutionFixesOverlayExtraction() throws Exception {
        Path experimentRoot = Path.of("").toAbsolutePath().normalize();
        Map<FontKind, Path> fonts = FontAssets.prepare(experimentRoot, temporary);
        Path source = temporary.resolve("source.pdf");
        OfficeExtractionInvestigation.createMinimalSource(source, "source office");
        String sourceDigest = FontAssets.digest(source);

        Path openedOnly = temporary.resolve("opened-only.pdf");
        Path unrelated = temporary.resolve("unrelated.pdf");
        Path office = temporary.resolve("office.pdf");
        OfficeExtractionInvestigation.stamp(
                source, openedOnly, null, fonts.get(FontKind.NOTO_SANS),
                BaseFont.IDENTITY_H, true, true, true);
        OfficeExtractionInvestigation.stamp(
                source, unrelated, List.of("CLAROS marker"), fonts.get(FontKind.NOTO_SANS),
                BaseFont.IDENTITY_H, true, true, true);
        OfficeExtractionInvestigation.stamp(
                source, office, List.of("CLAROS office overlay"), fonts.get(FontKind.NOTO_SANS),
                BaseFont.IDENTITY_H, true, true, true);

        OfficeExtractionInvestigation.CaseEvidence original = inspect(experimentRoot, "A", source);
        OfficeExtractionInvestigation.CaseEvidence caseB = inspect(experimentRoot, "B", openedOnly);
        OfficeExtractionInvestigation.CaseEvidence caseC = inspect(experimentRoot, "C", unrelated);
        OfficeExtractionInvestigation.CaseEvidence caseD = inspect(experimentRoot, "D", office);

        assertEquals("source office", original.pdfBoxText());
        assertEquals("source office", caseB.pdfBoxText());
        assertEquals("source office\nCLAROS marker", caseC.pdfBoxText());
        assertEquals("source office\nCLAROS ofce overlay", caseD.pdfBoxText());
        assertEquals(sourceDigest, FontAssets.digest(source));
        String sourceStream = original.contentStreams().getFirst().decodedSha256();
        assertTrue(caseB.contentStreams().stream().anyMatch(stream -> stream.decodedSha256().equals(sourceStream)));
        assertTrue(caseC.contentStreams().stream().anyMatch(stream -> stream.decodedSha256().equals(sourceStream)));
        assertTrue(caseD.contentStreams().stream().anyMatch(stream -> stream.decodedSha256().equals(sourceStream)));

        Path defaultOutput = OfficeExtractionInvestigation.stampMinimal(
                source, temporary.resolve("default.pdf"), fonts.get(FontKind.NOTO_SANS),
                BaseFont.IDENTITY_H, true, true, true);
        Path noSubsetOutput = OfficeExtractionInvestigation.stampMinimal(
                source, temporary.resolve("no-subset.pdf"), fonts.get(FontKind.NOTO_SANS),
                BaseFont.IDENTITY_H, true, false, true);
        Path fixedOutput = OfficeExtractionInvestigation.stampMinimal(
                source, temporary.resolve("fixed.pdf"), fonts.get(FontKind.NOTO_SANS),
                BaseFont.IDENTITY_H, true, true, false);

        OfficeExtractionInvestigation.CaseEvidence defaultCase = inspect(experimentRoot, "default", defaultOutput);
        OfficeExtractionInvestigation.CaseEvidence noSubsetCase = inspect(experimentRoot, "no-subset", noSubsetOutput);
        OfficeExtractionInvestigation.CaseEvidence fixedCase = inspect(experimentRoot, "fixed", fixedOutput);
        String exactWords = String.join("\n", OfficeExtractionInvestigation.WORDS);

        assertEquals("source office\n" + exactWords, fixedCase.pdfBoxText());
        assertFalse(defaultCase.pdfBoxText().endsWith(exactWords));
        assertFalse(noSubsetCase.pdfBoxText().endsWith(exactWords));
        assertTrue(defaultCase.pdfBoxText().contains("ofce\nofcial\nefcient\nfle\nfrst\nafnity\ndiferent"));
        String defaultCmap = notoFont(defaultCase).toUnicode();
        assertTrue(defaultCmap.contains("<0673><0673><0066>"), "ff maps only to the first f");
        assertTrue(defaultCmap.contains("<0674><0674><0066>"), "fi maps only to f");
        assertTrue(defaultCmap.contains("<0676><0676><0066>"), "ffi maps only to the first f");
        assertFalse(notoFont(fixedCase).toUnicode().contains("<0676>"));
    }

    private static OfficeExtractionInvestigation.CaseEvidence inspect(
            Path experimentRoot, String id, Path pdf) throws Exception {
        return OfficeExtractionInvestigation.inspect(id, experimentRoot, pdf);
    }

    private static OfficeExtractionInvestigation.FontEvidence notoFont(
            OfficeExtractionInvestigation.CaseEvidence evidence) {
        return evidence.fonts().stream()
                .filter(font -> font.baseFont().contains("NotoSans-Regular"))
                .findFirst()
                .orElseThrow();
    }
}
