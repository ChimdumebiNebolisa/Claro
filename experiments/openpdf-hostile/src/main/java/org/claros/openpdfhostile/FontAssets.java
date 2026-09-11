package org.claros.openpdfhostile;

import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Map;

public final class FontAssets {
    public static final String GOOGLE_FONTS_COMMIT = "5e35378e6bda803962ee6fd257e444a7d459660d";

    private static final Map<FontKind, RemoteFont> REMOTE_FONTS = Map.of(
            FontKind.NOTO_MATH, remote("ofl/notosansmath/NotoSansMath-Regular.ttf",
                    "3f495fe933c06786e4d5f6d86b8ee70b6753a68ee3b9d87528726de0f6e2c47d"),
            FontKind.NOTO_ARABIC, remote("ofl/notosansarabic/NotoSansArabic%5Bwdth,wght%5D.ttf",
                    "63111b5b2e074dd48cc67692e0a2726d86ee94c1c37fe8598257b7b4e87e869e"),
            FontKind.NOTO_HEBREW, remote("ofl/notosanshebrew/NotoSansHebrew%5Bwdth,wght%5D.ttf",
                    "7ef36a2c3593758cdb622e1bdef4f84523e92fbc3ccc667438dd80ff54c2de88"),
            FontKind.NOTO_CJK_SC, remote("ofl/notosanssc/NotoSansSC%5Bwght%5D.ttf",
                    "a3041811a78c361b1de50f953c805e0244951c21c5bd412f7232ef0d899af0da"),
            FontKind.NOTO_EMOJI, remote("ofl/notoemoji/NotoEmoji%5Bwght%5D.ttf",
                    "de6c18832938afc99caf132b39d6a30a19bac7f2e812e28db2535b4608d27551"));

    private FontAssets() {
    }

    public static Map<FontKind, Path> prepare(Path experimentRoot, Path targetRoot)
            throws IOException, InterruptedException {
        Path fontDir = targetRoot.resolve("fonts");
        Files.createDirectories(fontDir);
        Path localNoto = experimentRoot.resolve("../../assets/fonts/noto-sans/NotoSans-Regular.ttf")
                .normalize().toAbsolutePath();
        verify(localNoto, "b85c38ecea8a7cfb39c24e395a4007474fa5a4fc864f6ee33309eb4948d232d5");
        var result = new java.util.EnumMap<FontKind, Path>(FontKind.class);
        result.put(FontKind.NOTO_SANS, localNoto);

        for (var entry : REMOTE_FONTS.entrySet()) {
            Path destination = fontDir.resolve(entry.getKey().fileName());
            if (!Files.isRegularFile(destination) || !digest(destination).equals(entry.getValue().sha256())) {
                Path temporary = fontDir.resolve(entry.getKey().fileName() + ".download");
                HttpURLConnection connection = (HttpURLConnection) entry.getValue().uri().toURL().openConnection();
                connection.setInstanceFollowRedirects(true);
                connection.setRequestProperty("User-Agent", "Claros-OpenPDF-hostile-spike");
                connection.setConnectTimeout(30_000);
                connection.setReadTimeout(120_000);
                int status = connection.getResponseCode();
                if (status != HttpURLConnection.HTTP_OK) {
                    Files.deleteIfExists(temporary);
                    connection.disconnect();
                    throw new IOException("Font download failed with HTTP " + status);
                }
                try (InputStream input = connection.getInputStream()) {
                    Files.copy(input, temporary, StandardCopyOption.REPLACE_EXISTING);
                } finally {
                    connection.disconnect();
                }
                verify(temporary, entry.getValue().sha256());
                Files.move(temporary, destination, StandardCopyOption.REPLACE_EXISTING,
                        StandardCopyOption.ATOMIC_MOVE);
            }
            verify(destination, entry.getValue().sha256());
            result.put(entry.getKey(), destination);
        }
        return Map.copyOf(result);
    }

    public static String digest(Path path) throws IOException {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (InputStream input = Files.newInputStream(path)) {
                byte[] buffer = new byte[64 * 1024];
                int read;
                while ((read = input.read(buffer)) >= 0) {
                    digest.update(buffer, 0, read);
                }
            }
            return HexFormat.of().formatHex(digest.digest());
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException(error);
        }
    }

    private static void verify(Path path, String expected) throws IOException {
        if (!Files.isRegularFile(path)) {
            throw new IOException("Missing font asset: " + path);
        }
        String actual = digest(path);
        if (!actual.equals(expected)) {
            throw new IOException("Font checksum mismatch for " + path.getFileName());
        }
    }

    private static RemoteFont remote(String path, String sha256) {
        return new RemoteFont(
                URI.create("https://raw.githubusercontent.com/google/fonts/"
                        + GOOGLE_FONTS_COMMIT + "/" + path),
                sha256);
    }

    private record RemoteFont(URI uri, String sha256) {
    }
}
