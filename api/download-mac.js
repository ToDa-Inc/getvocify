const RELEASES = "https://api.github.com/repos/ToDa-Inc/getvocify-desktop/releases?per_page=30";
const FALLBACK = "https://github.com/ToDa-Inc/getvocify-desktop/releases";

// Sends the visitor to the newest Mac DMG (one app for Apple Silicon and Intel). GitHub's own "latest" link skips
// pre-releases and the file name carries the version, so we look the file up.
export default async function handler(req, res) {
  try {
    const r = await fetch(RELEASES, { headers: { Accept: "application/vnd.github+json" } });
    if (!r.ok) throw new Error(`GitHub ${r.status}`);
    const releases = await r.json();
    for (const release of releases) {
      if (release.draft) continue;
      const dmg = release.assets.find((a) => /^Vocify-.*-universal\.dmg$/.test(a.name));
      if (dmg) {
        res.setHeader("Cache-Control", "public, s-maxage=300, stale-while-revalidate=3600");
        res.redirect(302, dmg.browser_download_url);
        return;
      }
    }
    throw new Error("no Mac DMG in the latest releases");
  } catch (err) {
    console.error("download-mac:", err);
    res.setHeader("Cache-Control", "no-store");
    res.redirect(302, FALLBACK);
  }
}
