// Runs on meet.google.com: during a call, reports who Meet shows speaking a few times a second.
// Only display names leave the page, and only to the Vocify Mac app on this computer.
(async () => {
  const { MEET_SPEAKERS, isMeetCallPath, readMeetTiles, speakingNames } = await import(
    chrome.runtime.getURL('lib/meet-speakers.js')
  );
  const TICK_MS = 400;
  let inCall = false;

  const report = (speaking) => {
    try {
      chrome.runtime.sendMessage({ type: MEET_SPEAKERS, speaking }).catch(() => {});
    } catch {
      // The extension was updated or reloaded: this copy of the script is orphaned.
      clearInterval(timer);
    }
  };

  const timer = setInterval(() => {
    const tiles = isMeetCallPath(location.pathname) ? readMeetTiles(document) : [];
    if (tiles.length === 0) {
      if (inCall) report([]);
      inCall = false;
      return;
    }
    inCall = true;
    report(speakingNames(tiles));
  }, TICK_MS);
})();
