package org.claros.openpdfintegration;

/** Bounded test helper used only to prove that -Xmx terminates an over-budget JVM. */
public final class ResourceProbeMain {
    private ResourceProbeMain() {
    }

    public static void main(String[] args) {
        if (args.length != 1 || !"allocate-96-mib".equals(args[0])) {
            System.exit(2);
        }
        byte[] allocation = new byte[96 * 1024 * 1024];
        allocation[allocation.length - 1] = 1;
    }
}
