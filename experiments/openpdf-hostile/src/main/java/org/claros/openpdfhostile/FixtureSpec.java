package org.claros.openpdfhostile;

import java.util.List;

public record FixtureSpec(
        String id,
        String description,
        String sourceText,
        String overlayText,
        FontKind overlayFont,
        List<Anchor> anchors,
        int overlayPage,
        boolean unicodeCase,
        boolean continuation,
        boolean malformed,
        String userPassword,
        String ownerPassword) {

    public FixtureSpec {
        anchors = List.copyOf(anchors);
    }

    public boolean encrypted() {
        return userPassword != null;
    }
}

