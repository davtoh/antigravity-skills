(() => {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const docScrollH = document.documentElement.scrollHeight;
  const docScrollW = document.documentElement.scrollWidth;
  const scrollX = Math.round(window.scrollX || document.documentElement.scrollLeft || document.body.scrollLeft || 0);
  const scrollY = Math.round(window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0);

  function sanitizeSrc(rawSrc) {
    if (!rawSrc || typeof rawSrc !== 'string') return '';
    if (rawSrc.startsWith('data:') && rawSrc.length > 64) {
      return rawSrc.slice(0, 48) + `... [data URI truncated, length: ${rawSrc.length}]`;
    }
    return rawSrc;
  }

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

    const offsetFromParent = pr ? {
      left: Math.round(r.left - pr.left),
      top: Math.round(r.top - pr.top),
      right: Math.round(pr.right - r.right),
      bottom: Math.round(pr.bottom - r.bottom)
    } : null;

    const info = {
      tag: el.tagName.toLowerCase(),
      id: el.id || undefined,
      className: typeof el.className === 'string' && el.className ? el.className.trim().split(/\s+/).slice(0, 4).join('.') : undefined,
      rect: { x: Math.round(r.x), y: Math.round(r.y), width: Math.round(r.width), height: Math.round(r.height), bottom: Math.round(r.bottom) },
      overflowsParent,
      offsetFromParent,
      visible: r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden',
      style: {
        display: cs.display,
        position: cs.position,
        overflow: cs.overflow,
        maxHeight: cs.maxHeight,
        aspectRatio: cs.aspectRatio,
        objectFit: cs.objectFit,
        scrollSnapType: cs.scrollSnapType !== 'none' ? cs.scrollSnapType : undefined,
        scrollSnapAlign: cs.scrollSnapAlign !== 'none' ? cs.scrollSnapAlign : undefined
      },
    };

    if (el.scrollWidth > el.clientWidth || el.scrollHeight > el.clientHeight || el.scrollLeft > 0 || el.scrollTop > 0) {
      info.scroll = {
        scrollLeft: Math.round(el.scrollLeft),
        scrollTop: Math.round(el.scrollTop),
        scrollWidth: Math.round(el.scrollWidth),
        scrollHeight: Math.round(el.scrollHeight)
      };
    }

    if (el.tagName === 'VIDEO') {
      info.video = {
        src: sanitizeSrc(el.currentSrc || el.src),
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
        src: sanitizeSrc(el.currentSrc || el.src),
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

  function formatSelector(el) {
    const cls = typeof el.className === 'string' && el.className
      ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.')
      : '';
    return el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + cls;
  }

  const layoutOverflowWarnings = [];
  if (scrollX > 0) {
    layoutOverflowWarnings.push({
      selector: "window",
      warning: "Unintended root horizontal window scroll detected (scrollX > 0)",
      scrollX,
      scrollY
    });
  }

  let containerWarnCount = 0;
  for (const el of document.querySelectorAll('main, section, article, div, aside')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    const cs = window.getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    if (r.right > vw + 4 || (el.scrollHeight > el.clientHeight + 4 && cs.overflowY === 'hidden')) {
      layoutOverflowWarnings.push({
        selector: formatSelector(el),
        rect: { width: Math.round(r.width), height: Math.round(r.height), right: Math.round(r.right), bottom: Math.round(r.bottom) },
        scrollHeight: el.scrollHeight,
        clientHeight: el.clientHeight,
        overflowY: cs.overflowY
      });
      containerWarnCount += 1;
      if (containerWarnCount >= 15) break;
    }
  }

  let textOverflowCount = 0;
  for (const el of document.querySelectorAll('button, a, .badge, .menuitem, .video-action-menu')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    const cs = window.getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const isEllipsized = (cs.overflowX === 'hidden' || cs.overflowX === 'clip') && cs.textOverflow === 'ellipsis';
    const hasRiskStyle = cs.whiteSpace === 'nowrap' || cs.overflow === 'visible' || cs.overflowX === 'visible';
    if (!isEllipsized && hasRiskStyle && el.scrollWidth > el.clientWidth + 2) {
      layoutOverflowWarnings.push({
        selector: formatSelector(el),
        warning: "Horizontal text overflow detected (scrollWidth > clientWidth)",
        text: (el.textContent || '').trim().slice(0, 80),
        rect: { width: Math.round(r.width), height: Math.round(r.height), right: Math.round(r.right), bottom: Math.round(r.bottom) },
        scrollWidth: Math.round(el.scrollWidth),
        clientWidth: Math.round(el.clientWidth),
        whiteSpace: cs.whiteSpace,
        overflow: cs.overflow
      });
      textOverflowCount += 1;
      if (textOverflowCount >= 15) break;
    }
  }

  const flushControlWarnings = [];
  for (const container of document.querySelectorAll('header, nav, .toolbar, [role="toolbar"], .actions, .btn-row, div')) {
    const ccs = window.getComputedStyle(container);
    if (ccs.display !== 'flex' && ccs.display !== 'inline-flex') continue;
    if (ccs.visibility === 'hidden' || /btn-group|segmented|input-group/.test(container.className || '')) continue;
    const kids = Array.from(container.children).filter((k) => {
      const kr = k.getBoundingClientRect();
      const kcs = window.getComputedStyle(k);
      return kr.width > 0 && kr.height > 0 && kcs.display !== 'none' && k.matches('button, a, select, input');
    });
    for (let i = 0; i < kids.length - 1 && flushControlWarnings.length < 15; i += 1) {
      const a = kids[i].getBoundingClientRect(), b = kids[i + 1].getBoundingClientRect();
      const sameRow = Math.abs(a.top - b.top) < Math.min(a.height, b.height);
      const gap = sameRow ? (b.left - a.right) : (b.top - a.bottom);
      if (gap < 4) {
        flushControlWarnings.push({
          container: formatSelector(container),
          controls: [formatSelector(kids[i]), formatSelector(kids[i + 1])],
          gapPx: Math.round(gap * 10) / 10,
          warning: 'Adjacent interactive controls have < 4px spacing (flush/colliding)',
        });
      }
    }
  }

  const duplicateControlWarnings = [];
  const seenLabelsByScope = new Map();
  for (const btn of document.querySelectorAll('button, [role="button"]')) {
    const br = btn.getBoundingClientRect();
    const bcs = window.getComputedStyle(btn);
    if (br.width === 0 || br.height === 0 || bcs.display === 'none' || bcs.visibility === 'hidden') continue;
    const label = (btn.textContent || '').trim().replace(/\s+/g, ' ').toLowerCase();
    if (label.length < 2) continue;
    const scopeEl = btn.closest('.modal, section, dialog, [role="dialog"], main') || document.body;
    const scopeKey = `${formatSelector(scopeEl)}::${label}`;
    const count = (seenLabelsByScope.get(scopeKey) || 0) + 1;
    seenLabelsByScope.set(scopeKey, count);
    if (count === 2 && duplicateControlWarnings.length < 15) {
      duplicateControlWarnings.push({
        scope: formatSelector(scopeEl),
        label: (btn.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 60),
        warning: 'Duplicate visible button/control label in active view',
      });
    }
  }

  const brokenImageWarnings = [];
  for (const img of document.querySelectorAll('img')) {
    if (brokenImageWarnings.length >= 15) break;
    const ics = window.getComputedStyle(img);
    if (ics.display === 'none' || ics.visibility === 'hidden' || (img.offsetParent === null && ics.position !== 'fixed')) continue;
    const rawSrc = (img.getAttribute('src') || '').trim();
    const curSrc = (img.currentSrc || '').trim();
    if (!rawSrc || (img.complete && img.naturalWidth === 0) || (!curSrc && img.naturalWidth === 0)) {
      brokenImageWarnings.push({
        selector: formatSelector(img),
        src: sanitizeSrc(curSrc || rawSrc),
        naturalWidth: img.naturalWidth,
        complete: img.complete,
        warning: !rawSrc ? 'Visible <img> has empty or missing src attribute' : 'Visible <img> failed to load (naturalWidth === 0)',
      });
    }
  }

  const squeezedControlWarnings = [];
  for (const modal of document.querySelectorAll('.modal, dialog, [role="dialog"]')) {
    const mcs = window.getComputedStyle(modal);
    if (mcs.display === 'none' || mcs.visibility === 'hidden' || modal.getBoundingClientRect().width === 0) continue;
    for (const tbl of modal.querySelectorAll('.data-table')) {
      if (squeezedControlWarnings.length >= 15) break;
      const tr = tbl.getBoundingClientRect();
      if (tr.width > 0 && tbl.scrollWidth > tbl.clientWidth + 2) {
        squeezedControlWarnings.push({
          selector: formatSelector(tbl),
          scrollWidth: Math.round(tbl.scrollWidth),
          clientWidth: Math.round(tbl.clientWidth),
          warning: 'Modal .data-table horizontally squeezed (scrollWidth > clientWidth)',
        });
      }
    }
    for (const ctrl of modal.querySelectorAll('input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]):not([type="color"]), select, textarea')) {
      if (squeezedControlWarnings.length >= 15) break;
      const cr = ctrl.getBoundingClientRect();
      const ccs = window.getComputedStyle(ctrl);
      if (cr.width > 0 && ccs.display !== 'none' && (cr.width < 48 || ctrl.scrollWidth > ctrl.clientWidth + 2)) {
        squeezedControlWarnings.push({
          selector: formatSelector(ctrl),
          width: Math.round(cr.width),
          scrollWidth: Math.round(ctrl.scrollWidth),
          clientWidth: Math.round(ctrl.clientWidth),
          warning: 'Modal form control horizontally squeezed',
        });
      }
    }
  }

  const report = {
    title: document.title,
    url: window.location.href,
    viewport: {
      width: vw,
      height: vh,
      scrollWidth: docScrollW,
      scrollHeight: docScrollH,
      scrollX,
      scrollY,
      hasVerticalScrollbar: docScrollH > vh,
      hasHorizontalScrollbar: docScrollW > vw,
      hasHorizontalWindowScroll: scrollX > 0
    },
    mediaElements,
    queriedSelectors: customSelectors.length ? queriedSelectors : undefined,
    layoutOverflowWarnings,
    flushControlWarnings,
    duplicateControlWarnings,
    brokenImageWarnings,
    squeezedControlWarnings,
    layoutJitterWarnings: []
  };

  if (window.__FRONTIER_EXTRA_LAYOUT_CHECKS__) {
    window.__FRONTIER_EXTRA_LAYOUT_CHECKS__.verifyDataSvgImages(brokenImageWarnings, formatSelector, sanitizeSrc);
    window.__FRONTIER_EXTRA_LAYOUT_CHECKS__.checkFlexChildBoxOverflow(layoutOverflowWarnings, formatSelector);
    window.__FRONTIER_EXTRA_LAYOUT_CHECKS__.checkCanvasLuminance(report);
  }

  const stabilityMs = Number(window.__FRONTIER_STABILITY_MS__ || 0);
  if (!(stabilityMs > 0)) return report;

  return (async () => {
    const watchNodes = Array.from(document.querySelectorAll('header, nav, [class*="hud"], [class*="header"], [class*="card"], [class*="panel"]')).slice(0, 40);
    const snap = () => watchNodes.map((el) => {
      const r = el.getBoundingClientRect();
      return { el, x: r.x, y: r.y, w: r.width, h: r.height };
    });
    const base = snap();
    const stepMs = Math.max(50, Math.round(stabilityMs / 3));
    for (let s = 0; s < 3; s += 1) {
      await new Promise((r) => setTimeout(r, stepMs));
      const cur = snap();
      for (let i = 0; i < cur.length; i += 1) {
        const dx = Math.abs(cur[i].x - base[i].x), dy = Math.abs(cur[i].y - base[i].y);
        const dw = Math.abs(cur[i].w - base[i].w), dh = Math.abs(cur[i].h - base[i].h);
        if (dx > 2 || dy > 2 || dw > 2 || dh > 2) {
          report.layoutJitterWarnings.push({
            selector: formatSelector(cur[i].el),
            delta: { dx: Math.round(dx), dy: Math.round(dy), dw: Math.round(dw), dh: Math.round(dh) },
            warning: 'Layout instability / CLS jitter (>2px DOMRect shift) during live sampling',
          });
          base[i] = cur[i];
        }
      }
    }
    return report;
  })();
})()
