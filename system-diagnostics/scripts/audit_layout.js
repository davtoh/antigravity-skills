(() => {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const docScrollH = document.documentElement.scrollHeight;
  const docScrollW = document.documentElement.scrollWidth;

  function describeEl(el) {
    const r = el.getBoundingClientRect();
    const cs = window.getComputedStyle(el);
    const parent = el.parentElement;
    const pr = parent ? parent.getBoundingClientRect() : null;
    const overflowsParent = pr ? (
      Math.round(r.right) > Math.round(pr.right) + 2 ||
      Math.round(r.bottom) > Math.round(pr.bottom) + 2 ||
      Math.round(r.left) < Math.round(pr.left) - 2 ||
      Math.round(r.top) < Math.round(pr.top) - 2
    ) : false;

    const info = {
      tag: el.tagName.toLowerCase(),
      id: el.id || undefined,
      className: typeof el.className === 'string' && el.className ? el.className.trim().split(/\s+/).slice(0, 4).join('.') : undefined,
      rect: { x: Math.round(r.x), y: Math.round(r.y), width: Math.round(r.width), height: Math.round(r.height), bottom: Math.round(r.bottom) },
      overflowsParent,
      visible: r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden',
      style: { display: cs.display, position: cs.position, overflow: cs.overflow, maxHeight: cs.maxHeight, aspectRatio: cs.aspectRatio, objectFit: cs.objectFit },
    };
    if (el.tagName === 'VIDEO') {
      info.video = {
        src: el.currentSrc || el.src,
        paused: el.paused,
        ended: el.ended,
        currentTime: Number(el.currentTime.toFixed(2)),
        duration: Number((el.duration || 0).toFixed(2)),
        videoWidth: el.videoWidth,
        videoHeight: el.videoHeight,
        readyState: el.readyState,
        error: el.error ? el.error.code : null
      };
    } else if (el.tagName === 'IMG') {
      info.img = {
        src: el.currentSrc || el.src,
        naturalWidth: el.naturalWidth,
        naturalHeight: el.naturalHeight,
        complete: el.complete
      };
    } else if (el.tagName === 'BUTTON' || el.tagName.startsWith('H') || el.tagName === 'SPAN') {
      info.text = el.textContent.trim().slice(0, 80);
    }
    return info;
  }

  const mediaElements = Array.from(document.querySelectorAll('video, img, canvas')).map(describeEl);
  const customSelectors = window.__FRONTIER_SELECTORS__ || [];
  const queriedSelectors = {};
  for (const sel of customSelectors) {
    const el = document.querySelector(sel);
    queriedSelectors[sel] = el ? describeEl(el) : null;
  }

  const layoutOverflowWarnings = [];
  for (const el of document.querySelectorAll('main, section, article, div, aside')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    const cs = window.getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    if (r.right > vw + 4 || (el.scrollHeight > el.clientHeight + 4 && cs.overflowY === 'hidden')) {
      layoutOverflowWarnings.push({
        selector: (el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (typeof el.className === 'string' && el.className ? '.' + el.className.trim().split(/\s+/)[0] : '')),
        rect: { width: Math.round(r.width), height: Math.round(r.height), right: Math.round(r.right), bottom: Math.round(r.bottom) },
        scrollHeight: el.scrollHeight,
        clientHeight: el.clientHeight,
        overflowY: cs.overflowY
      });
      if (layoutOverflowWarnings.length >= 15) break;
    }
  }

  return {
    title: document.title,
    url: window.location.href,
    viewport: { width: vw, height: vh, scrollWidth: docScrollW, scrollHeight: docScrollH, hasVerticalScrollbar: docScrollH > vh, hasHorizontalScrollbar: docScrollW > vw },
    mediaElements,
    queriedSelectors: customSelectors.length ? queriedSelectors : undefined,
    layoutOverflowWarnings
  };
})()
