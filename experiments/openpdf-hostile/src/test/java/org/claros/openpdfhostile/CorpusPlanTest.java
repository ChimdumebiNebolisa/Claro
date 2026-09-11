package org.claros.openpdfhostile;

import org.junit.jupiter.api.Test;

import java.util.Set;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CorpusPlanTest {
    @Test
    void corpusCoversEveryRequestedHostileClassAndExplicitCapabilityProbe() {
        Set<String> ids = CorpusPlan.fixtures().stream().map(FixtureSpec::id).collect(Collectors.toSet());
        assertEquals(CorpusPlan.fixtures().size(), ids.size());
        assertTrue(ids.containsAll(Set.of(
                "normal-letter", "a4", "mixed-page-sizes",
                "rotated-90", "rotated-180", "rotated-270", "cropbox-offset",
                "trim-bleed-boxes", "mixed-rotations", "annotations", "acroform",
                "embedded-font", "unicode-text", "accented-latin", "mathematical-symbols",
                "cjk", "arabic-rtl", "hebrew-rtl", "long-multiline-answer", "existing-images",
                "vector-graphics", "transparency", "object-stream-heavy", "office-style",
                "scanned-image-only", "large-multipage", "encrypted", "malformed-readable",
                "outlines", "links", "metadata", "user-unit-2", "emoji")));
        assertTrue(CorpusPlan.fixtures().size() >= 30);
    }
}
