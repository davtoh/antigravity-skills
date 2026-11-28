(() => {
  function verifyDataSvgImages(brokenImageWarnings, formatSelector, sanitizeSrc) {
    if (typeof DOMParser === 'undefined') return;
    for (const img of document.querySelectorAll('img')) {
      if (brokenImageWarnings.length >= 15) break;
      const ics = window.getComputedStyle(img);
      if (ics.display === 'none' || ics.visibility === 'hidden') continue;
      const rawSrc = (img.getAttribute('src') || '').trim();
      if (!rawSrc.startsWith('data:image/svg+xml')) continue;
      const commaIdx = rawSrc.indexOf(',');
      if (commaIdx < 0) continue;
      try {
        const meta = rawSrc.slice(0, commaIdx).toLowerCase();
        const payload = rawSrc.slice(commaIdx + 1);
        const xmlText = meta.includes(';base64') ? atob(payload) : decodeURIComponent(payload);
        const doc = new DOMParser().parseFromString(xmlText, 'image/svg+xml');
        const hasErr = Boolean(doc.querySelector('parsererror')) || !doc.documentElement || doc.documentElement.nodeName.toLowerCase() !== 'svg';
        if (hasErr) {
          brokenImageWarnings.push({
            selector: formatSelector(img),
            src: sanitizeSrc(rawSrc),
            warning: 'Visible data:image/svg+xml failed XML/SVG parse',
          });
        }
      } catch (_err) {
        brokenImageWarnings.push({
          selector: formatSelector(img),
          src: sanitizeSrc(rawSrc),
          warning: 'Visible data:image/svg+xml failed base64/URI decode',
        });
      }
    }
  }

  function checkFlexChildBoxOverflow(layoutOverflowWarnings, formatSelector) {
    let count = 0;
    for (const parent of document.querySelectorAll('div, section, header, nav, form, .toolbar')) {
      if (count >= 15) break;
      const pcs = window.getComputedStyle(parent);
      if ((pcs.display !== 'flex' && pcs.display !== 'inline-flex') || pcs.display === 'none' || pcs.visibility === 'hidden') continue;
      const pr = parent.getBoundingClientRect();
      if (pr.width <= 0 || pr.height <= 0) continue;
      for (const child of parent.children) {
        const ccs = window.getComputedStyle(child);
        if (ccs.display === 'none' || ccs.visibility === 'hidden' || ccs.position === 'absolute' || ccs.position === 'fixed') continue;
        const cr = child.getBoundingClientRect();
        if (cr.width <= 0 || cr.height <= 0) continue;
        if (cr.right > pr.right + 2 || cr.left < pr.left - 2) {
          layoutOverflowWarnings.push({
            selector: formatSelector(child),
            parent: formatSelector(parent),
            warning: 'Flex child bounding box overflows parent container',
            childRight: Math.round(cr.right),
            parentRight: Math.round(pr.right),
          });
          count += 1;
          break;
        }
      }
    }
  }

  function checkCanvasLuminance(report) {
    const blankCanvasWarnings = [];
    for (const cvs of document.querySelectorAll('canvas')) {
      const ccs = window.getComputedStyle(cvs);
      if (ccs.display === 'none' || ccs.visibility === 'hidden') continue;
      const cr = cvs.getBoundingClientRect();
      if (cr.width <= 0 || cr.height <= 0 || cvs.width <= 0 || cvs.height <= 0) continue;
      const isEnroll = /enroll|freeze|snapshot/i.test(cvs.id || '') || cvs.hasAttribute('data-check-luminance');
      if (!isEnroll) continue;
      try {
        const ctx = cvs.getContext('2d');
        if (!ctx) continue;
        const w = Math.min(cvs.width, 64), h = Math.min(cvs.height, 64);
        const data = ctx.getImageData(0, 0, w, h).data;
        let maxLum = 0;
        for (let i = 0; i < data.length; i += 16) {
          const lum = data[i] + data[i + 1] + data[i + 2];
          if (lum > maxLum) { maxLum = lum; break; }
        }
        if (maxLum === 0) {
          blankCanvasWarnings.push({
            selector: cvs.id ? `canvas#${cvs.id}` : 'canvas',
            width: cvs.width,
            height: cvs.height,
            warning: 'Enrollment/preview canvas has zero luminance (blank first frame)',
          });
        }
      } catch (_err) {
        // Cross-origin tainted canvas; ignore
      }
    }
    report.blankCanvasWarnings = blankCanvasWarnings;
  }

  window.__FRONTIER_EXTRA_LAYOUT_CHECKS__ = {
    verifyDataSvgImages,
    checkFlexChildBoxOverflow,
    checkCanvasLuminance,
  };
})();
