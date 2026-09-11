package org.claros.openpdfhostile;

import java.util.List;

public final class CorpusPlan {
    public static final String ENCRYPTED_USER_PASSWORD = "claros-user-test";
    public static final String ENCRYPTED_OWNER_PASSWORD = "claros-owner-test";

    private CorpusPlan() {
    }

    public static List<FixtureSpec> fixtures() {
        List<Anchor> center = List.of(Anchor.CENTER);
        return List.of(
                fixture("normal-letter", "Normal US Letter PDF", "Synthetic US Letter source",
                        "A(B) \\ %", FontKind.NOTO_SANS,
                        List.of(Anchor.UPPER_LEFT, Anchor.UPPER_RIGHT, Anchor.CENTER,
                                Anchor.LOWER_LEFT, Anchor.LOWER_RIGHT), 1, false),
                fixture("a4", "A4 PDF", "Synthetic A4 source", "CLAROS A4 overlay",
                        FontKind.NOTO_SANS, center, 1, false),
                fixture("mixed-page-sizes", "Mixed page sizes", "Mixed Letter, A4, and legal pages",
                        "CLAROS mixed-size overlay", FontKind.NOTO_SANS, center, 2, false),
                fixture("rotated-90", "90-degree rotated page", "Rotation 90 source",
                        "CLAROS rotate 90", FontKind.NOTO_SANS, center, 1, false),
                fixture("rotated-180", "180-degree rotated page", "Rotation 180 source",
                        "CLAROS rotate 180", FontKind.NOTO_SANS, center, 1, false),
                fixture("rotated-270", "270-degree rotated page", "Rotation 270 source",
                        "CLAROS rotate 270", FontKind.NOTO_SANS, center, 1, false),
                fixture("cropbox-offset", "CropBox different from MediaBox", "Offset CropBox source",
                        "crop", FontKind.NOTO_SANS,
                        List.of(Anchor.CROP_TOP_LEFT, Anchor.CROP_BOTTOM_RIGHT), 1, false),
                fixture("trim-bleed-boxes", "TrimBox and BleedBox", "Trim and bleed source",
                        "CLAROS trim bleed", FontKind.NOTO_SANS, center, 1, false),
                fixture("mixed-rotations", "Different rotations on each page", "Mixed rotations source",
                        "CLAROS mixed rotation", FontKind.NOTO_SANS, center, 4, false),
                fixture("annotations", "Existing text annotation", "Annotation source",
                        "CLAROS annotation overlay", FontKind.NOTO_SANS, center, 1, false),
                fixture("acroform", "Existing AcroForm text field", "AcroForm source",
                        "CLAROS AcroForm overlay", FontKind.NOTO_SANS, center, 1, false),
                fixture("embedded-font", "Existing embedded font", "Embedded Noto Sans source",
                        "CLAROS embedded font", FontKind.NOTO_SANS, center, 1, false),
                fixture("unicode-text", "Unicode punctuation and names", "Zoë — José — café",
                        "Zoë says “café”—exactly.", FontKind.NOTO_SANS, center, 1, true),
                fixture("accented-latin", "Accented Latin characters", "é ñ ü source",
                        "é ñ ü à ç å", FontKind.NOTO_SANS, center, 1, true),
                fixture("mathematical-symbols", "Greek and mathematical symbols", "α β Γ ∑ √ ≠ ≤ ≥ ∫",
                        "α β Γ ∑ √ ≠ ≤ ≥ ∫", FontKind.NOTO_MATH, center, 1, true),
                fixture("cjk", "CJK non-Latin script", "中文源文档",
                        "中文答案：光合作用", FontKind.NOTO_CJK_SC, center, 1, true),
                fixture("arabic-rtl", "Arabic right-to-left text", "مرحبا بالعالم",
                        "الإجابة العربية الدقيقة", FontKind.NOTO_ARABIC, center, 1, true),
                fixture("hebrew-rtl", "Hebrew right-to-left text", "שלום עולם",
                        "תשובה מדויקת בעברית", FontKind.NOTO_HEBREW, center, 1, true),
                new FixtureSpec("long-multiline-answer", "Long multiline continuation answer",
                        "Long answer source", "CLAROS continuation marker", FontKind.NOTO_SANS,
                        center, 1, false, true, false, null, null),
                fixture("existing-images", "Existing raster images", "Image source",
                        "CLAROS image overlay", FontKind.NOTO_SANS, center, 1, false),
                fixture("vector-graphics", "Existing vector graphics", "Vector source",
                        "CLAROS vector overlay", FontKind.NOTO_SANS, center, 1, false),
                fixture("transparency", "Existing transparency", "Transparency source",
                        "CLAROS transparency overlay", FontKind.NOTO_SANS, center, 1, false),
                fixture("object-stream-heavy", "Compressed object-stream-heavy PDF", "Compressed source",
                        "CLAROS object stream", FontKind.NOTO_SANS, center, 1, false),
                fixture("office-style", "Synthetic office-style document", "Office-style source",
                        "CLAROS office overlay", FontKind.NOTO_SANS, center, 1, false),
                fixture("scanned-image-only", "Scanned image-only page", "",
                        "CLAROS scan overlay", FontKind.NOTO_SANS, center, 1, false),
                fixture("large-multipage", "Large 60-page PDF", "Large source page",
                        "CLAROS page 60 overlay", FontKind.NOTO_SANS, center, 60, false),
                new FixtureSpec("encrypted", "Encrypted PDF with known password", "Encrypted source",
                        "CLAROS encrypted overlay", FontKind.NOTO_SANS, center, 1, false,
                        false, false, ENCRYPTED_USER_PASSWORD, ENCRYPTED_OWNER_PASSWORD),
                new FixtureSpec("malformed-readable", "Malformed but recoverable xref", "Recoverable source",
                        "CLAROS recovered overlay", FontKind.NOTO_SANS, center, 1, false,
                        false, true, null, null),
                fixture("outlines", "Existing bookmarks and outlines", "Outline source",
                        "CLAROS outline overlay", FontKind.NOTO_SANS, center, 1, false),
                fixture("links", "Existing URI link annotation", "Link source",
                        "CLAROS link overlay", FontKind.NOTO_SANS, center, 1, false),
                fixture("metadata", "Existing document metadata", "Metadata source",
                        "CLAROS metadata overlay", FontKind.NOTO_SANS, center, 1, false),
                fixture("user-unit-2", "Non-default UserUnit of 2", "UserUnit source",
                        "CLAROS UserUnit overlay", FontKind.NOTO_SANS, center, 1, false),
                fixture("emoji", "Emoji capability probe", "😀",
                        "😀", FontKind.NOTO_EMOJI, center, 1, true));
    }

    private static FixtureSpec fixture(
            String id,
            String description,
            String sourceText,
            String overlayText,
            FontKind font,
            List<Anchor> anchors,
            int page,
            boolean unicodeCase) {
        return new FixtureSpec(id, description, sourceText, overlayText, font, anchors, page,
                unicodeCase, false, false, null, null);
    }
}
