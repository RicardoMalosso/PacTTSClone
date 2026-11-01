// Lazy bug-guide player with readiness, autoplay, and cleanup.
import {$, el, link, t} from './dom.js';
import {tab} from './navigation.js';
import {dashboard} from './state.js';

let bugVideoTimer = null;

let bugLinkTimer = null;

let bugVideoOpen = false;

let bugPlayer = null;

let youtubeApiPromise = null;

let bugVideoRequest = 0;

function stopBugVideo() {
  bugVideoRequest++;
  clearTimeout(bugVideoTimer); bugVideoTimer = null;
  clearTimeout(bugLinkTimer); bugLinkTimer = null; $('bug-youtube-link').hidden = true;
  bugVideoOpen = false; dashboard.bugPlayerReady = false;
  if (bugPlayer) { bugPlayer.destroy(); bugPlayer = null; }
  $('bug-video').replaceChildren();
  document.querySelector('[data-tab="bugs"]').removeAttribute('aria-busy');
}

function youtubeApi() {
  if (window.YT?.Player) return Promise.resolve();
  if (!youtubeApiPromise) youtubeApiPromise = new Promise((resolve, reject) => {
    window.onYouTubeIframeAPIReady = resolve;
    const script = el('script', {src: 'https://www.youtube.com/iframe_api'});
    script.onerror = () => { youtubeApiPromise = null; script.remove(); reject(new Error('Cannot load video player. Try again or use the YouTube link.')); };
    document.head.append(script);
  });
  return youtubeApiPromise;
}

async function openBugVideo() {
  if (bugVideoOpen) return;
  bugVideoOpen = true;
  const request = ++bugVideoRequest;
  document.querySelector('[data-tab="bugs"]').setAttribute('aria-busy', 'true');
  $('health').textContent = t('Loading bug reporting video…');
  bugVideoTimer = setTimeout(() => {
    if (request !== bugVideoRequest) return;
    stopBugVideo();
    $('health').replaceChildren(t('Video player unavailable. '), link('Watch on YouTube ↗', 'https://youtu.be/b2eEl2oKXLA'));
  }, 20000);
  try {
    await youtubeApi();
    if (!bugVideoOpen || request !== bugVideoRequest) return;
    const mount = el('div', {id: 'bug-player-mount'}); $('bug-video').append(mount);
    bugPlayer = new YT.Player(mount, {
      host: 'https://www.youtube-nocookie.com', videoId: 'b2eEl2oKXLA',
      playerVars: {autoplay: 0, rel: 0, playsinline: 1},
      events: {
        onReady: event => {
          if (!bugVideoOpen || request !== bugVideoRequest) return;
          clearTimeout(bugVideoTimer);
          dashboard.bugPlayerReady = true;
          event.target.getIframe().title = t('Bug reporting guide');
          document.querySelector('[data-tab="bugs"]').removeAttribute('aria-busy');
          tab('bugs');
          // The direct YouTube link appears two seconds after this pane opens.
          $('bug-youtube-link').hidden = true;
          clearTimeout(bugLinkTimer);
          bugLinkTimer = setTimeout(() => {
            if (bugVideoOpen && request === bugVideoRequest && !$('pane-bugs').hidden) {
              $('bug-youtube-link').hidden = false;
            }
          }, 2000);
          window.Locale.bind($('bug-video-status'), 'If autoplay is blocked, press play in the video.');
          bugVideoTimer = setTimeout(() => {
            if (bugVideoOpen && request === bugVideoRequest) event.target.playVideo();
          }, 200);
        },
        onError: () => {
          if (request !== bugVideoRequest) return;
          stopBugVideo(); $('health').textContent = t('Video unavailable. Open the bug reporting guide on YouTube.');
        }
      }
    });
  } catch (error) {
    if (request === bugVideoRequest) { stopBugVideo(); $('health').textContent = error.message; }
  }
}

export {openBugVideo, stopBugVideo};
