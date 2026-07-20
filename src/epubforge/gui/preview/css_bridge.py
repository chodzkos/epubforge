"""Skrypt ApplicationWorld zbierający rzeczywistą kaskadę wybranego elementu."""

# CSSOM i getComputedStyle pozostają źródłem prawdy. Skrypt tylko opisuje wynik
# Chromium oraz podstawową kolejność kaskady autora potrzebną do wyjaśnienia v1.
INSPECT_SCRIPT = r"""
((requestedNodeId) => {
  const esc = value => (window.CSS && CSS.escape) ? CSS.escape(value) : value.replace(/["\\]/g, '\\$&');
  let element = requestedNodeId
    ? document.querySelector('[data-epubforge-node-id="' + esc(requestedNodeId) + '"]')
    : document.querySelector('[data-epubforge-active-node]');
  if (!element) return {available: false, error: 'Nie zaznaczono elementu w podglądzie.'};

  const computed = getComputedStyle(element);
  const inheritedNames = new Set([
    'color','cursor','direction','font','font-family','font-feature-settings','font-kerning',
    'font-size','font-stretch','font-style','font-variant','font-weight','letter-spacing',
    'line-height','list-style','orphans','quotes','text-align','text-indent','text-transform',
    'visibility','white-space','widows','word-spacing','writing-mode'
  ]);
  const specificity = selector => {
    // v1: zwykłe selektory DOM. Funkcyjne pseudoklasy są widocznym ograniczeniem.
    let s = selector.replace(/:where\([^)]*\)/g, '');
    const a = (s.match(/#[\w-]+/g) || []).length;
    const b = (s.match(/\.[\w-]+|\[[^\]]+\]|:(?!:)[\w-]+(?:\([^)]*\))?/g) || []).length;
    s = s.replace(/#[\w-]+|\.[\w-]+|\[[^\]]+\]|::[\w-]+|:(?!:)[\w-]+(?:\([^)]*\))?/g, ' ');
    const c = (s.match(/(^|[>+~\s,])(?:[a-zA-Z][\w-]*|\*)/g) || [])
      .filter(x => !x.trim().endsWith('*')).length + (selector.match(/::[\w-]+/g) || []).length;
    return [a,b,c];
  };
  const bestSpecificity = selectorText => {
    let best = [0,0,0];
    for (const selector of selectorText.split(',')) {
      try {
        if (!element.matches(selector.trim())) continue;
        const value = specificity(selector);
        if (value[0] > best[0] || (value[0] === best[0] && value[1] > best[1]) ||
            (value[0] === best[0] && value[1] === best[1] && value[2] > best[2])) best = value;
      } catch (_) {}
    }
    return best;
  };
  const contextsActive = contexts => contexts.every(ctx => {
    if (ctx.type === 'media') return matchMedia(ctx.condition).matches;
    if (ctx.type === 'supports') { try { return CSS.supports(ctx.condition); } catch (_) { return false; } }
    return true;
  });
  const declarations = [];
  const rules = [];
  const limitations = new Set([
    'Pseudoelementy, animacje i transitions są tylko do odczytu.',
    '@layer, @container, @scope oraz złożone var() mają ograniczoną analizę.',
    'Pełne drzewo stylów user-agent nie jest prezentowane.',
    'Shorthandy bez jednoznacznego spanu deklaracji są edytowane wyłącznie w obrębie całej reguły.',
    'Font użyty dla konkretnego glifu nie jest ujawniany przez WebEngine; pokazano rodzinę computed i fallbacki.'
  ]);
  let sourceOrder = 0;
  const pathFromHref = href => {
    try { const url = new URL(href); return decodeURIComponent(url.pathname.replace(/^\//, '')); }
    catch (_) { return null; }
  };
  const walk = (ruleList, sheetPath, path, contexts) => {
    for (let index = 0; index < ruleList.length; index++) {
      const rule = ruleList[index];
      const rulePath = path.concat(index);
      const type = String(rule.constructor && rule.constructor.name || 'CSSRule');
      if (rule instanceof CSSStyleRule) {
        let matched = false;
        try { matched = element.matches(rule.selectorText); } catch (_) { limitations.add('Nierozpoznany selektor: ' + rule.selectorText); }
        if (/:(is|not|has|where)\(/.test(rule.selectorText)) limitations.add('Specyficzność złożonych pseudoklas funkcyjnych jest przybliżona: ' + rule.selectorText);
        const active = contextsActive(contexts);
        const spec = bestSpecificity(rule.selectorText);
        const record = {
          selector: rule.selectorText, stylesheet_path: sheetPath, rule_path: rulePath,
          contexts, active, matched, specificity: spec, order: sourceOrder++, declarations: []
        };
        for (let i = 0; i < rule.style.length; i++) {
          const property = rule.style[i];
          const decl = {
            property, declared: rule.style.getPropertyValue(property).trim(),
            important: rule.style.getPropertyPriority(property) === 'important',
            computed: computed.getPropertyValue(property).trim(), active, matched,
            specificity: spec, order: record.order, inline: false
          };
          if (matched) {
            record.declarations.push(decl);
            declarations.push(decl);
          }
        }
        if (matched) rules.push(record);
      } else if (rule.type === CSSRule.IMPORT_RULE && rule.styleSheet) {
        const importedPath = pathFromHref(rule.href);
        const importedContexts = rule.media && rule.media.mediaText ? contexts.concat({type:'media', condition:rule.media.mediaText}) : contexts;
        try { walk(rule.styleSheet.cssRules, importedPath, [], importedContexts); }
        catch (_) { limitations.add('Nie odczytano importowanego arkusza: ' + (importedPath || rule.href)); }
      } else if (rule.cssRules) {
        let context = {type: type.replace(/^CSS|Rule$/g, '').toLowerCase(), condition: rule.conditionText || rule.name || ''};
        if (rule instanceof CSSMediaRule) context.type = 'media';
        else if (typeof CSSSupportsRule !== 'undefined' && rule instanceof CSSSupportsRule) context.type = 'supports';
        else if (!['media','supports'].includes(context.type)) limitations.add('Ograniczona analiza ' + type + '.');
        walk(rule.cssRules, sheetPath, rulePath, contexts.concat(context));
      } else if (![CSSRule.FONT_FACE_RULE, CSSRule.IMPORT_RULE].includes(rule.type)) {
        limitations.add('Nierozpoznana reguła CSSOM: ' + type + '.');
      }
    }
  };
  for (const sheet of Array.from(document.styleSheets)) {
    const owner = sheet.ownerNode;
    if (owner && owner.id && owner.id.startsWith('epubforge-') && owner.id !== 'epubforge-css-preview-layer') continue;
    const path = owner && owner.dataset ? (owner.dataset.epubforgePath || null) : null;
    try { walk(sheet.cssRules, path, [], []); }
    catch (_) { limitations.add('Arkusz niedostępny dla CSSOM: ' + (path || 'inline') + '.'); }
  }
  const inlineRule = {selector: 'element.style', stylesheet_path: null, rule_path: ['inline'], contexts: [], active: true, matched: true, specificity: [1,0,0,0], order: sourceOrder++, declarations: []};
  for (let i = 0; i < element.style.length; i++) {
    const property = element.style[i];
    const decl = {property, declared: element.style.getPropertyValue(property).trim(), important: element.style.getPropertyPriority(property) === 'important', computed: computed.getPropertyValue(property).trim(), active: true, matched: true, specificity: [1,0,0,0], order: inlineRule.order, inline: true};
    inlineRule.declarations.push(decl); declarations.push(decl);
  }
  if (inlineRule.declarations.length) rules.push(inlineRule);

  // Klasyfikacja wyłącznie podstawowej kaskady v1; computed value nadal pochodzi z Chromium.
  const byProperty = new Map();
  const winners = new Map();
  declarations.forEach(d => { if (d.active && d.matched) (byProperty.get(d.property) || byProperty.set(d.property, []).get(d.property)).push(d); });
  for (const [property, list] of byProperty) {
    list.sort((a,b) => Number(a.important)-Number(b.important) || Number(a.inline)-Number(b.inline) ||
      (a.specificity[0]-b.specificity[0]) || (a.specificity[1]-b.specificity[1]) ||
      (a.specificity[2]-b.specificity[2]) || (a.specificity[3]||0)-(b.specificity[3]||0) || a.order-b.order);
    const winner = list[list.length-1];
    winners.set(property, winner);
    list.forEach(d => { d.state = d === winner ? 'winning' : 'lost'; d.winner_order = winner.order; });
  }
  const shorthands = new Set(['margin','padding','border','font','background','list-style','flex','grid']);
  declarations.forEach(d => {
    if (d.state !== 'winning' || !shorthands.has(d.property)) return;
    if (Array.from(winners).some(([name, winner]) => name.startsWith(d.property + '-') && winner !== d)) d.state = 'partial';
  });
  declarations.forEach(d => { if (!d.active) d.state = 'inactive'; else if (!d.matched) d.state = 'lost'; });

  const parentComputed = element.parentElement ? getComputedStyle(element.parentElement) : null;
  const inherited = [];
  if (parentComputed) inheritedNames.forEach(property => {
    if (!byProperty.has(property) && computed.getPropertyValue(property) === parentComputed.getPropertyValue(property))
      inherited.push({property, computed: computed.getPropertyValue(property).trim(), from: element.parentElement.localName});
  });
  const rect = element.getBoundingClientRect();
  const side = (prefix, name) => ({top: computed.getPropertyValue(prefix+'-top'+name), right: computed.getPropertyValue(prefix+'-right'+name), bottom: computed.getPropertyValue(prefix+'-bottom'+name), left: computed.getPropertyValue(prefix+'-left'+name)});
  const breadcrumb = [];
  for (let n = element; n && n.nodeType === 1; n = n.parentElement) breadcrumb.unshift(n.localName + (n.id ? '#'+n.id : '') + Array.from(n.classList || []).slice(0,3).map(c=>'.'+c).join(''));
  const family = computed.fontFamily;
  const candidates = family.split(',').map(x => x.trim().replace(/^['"]|['"]$/g, '')).filter(Boolean);
  let embedded = false, fontStatus = 'font systemowy lub fallback';
  if (document.fonts) {
    const faces = [];
    document.fonts.forEach(face => { if ((face.family || '').replace(/^['"]|['"]$/g, '') === (candidates[0] || '')) faces.push(face); });
    embedded = faces.some(face => face.status === 'loaded');
    if (faces.length) fontStatus = embedded ? 'osadzony, gotowy' : faces.map(face => face.status).join(', ');
  }
  return {
    available: true, node_id: element.getAttribute('data-epubforge-node-id'), breadcrumb,
    element: {tag: element.localName, id: element.id || '', classes: Array.from(element.classList || []), text: (element.textContent || '').trim().replace(/\s+/g,' ').slice(0,160)},
    box: {margin: side('margin',''), border: side('border','-width'), padding: side('padding',''), content: {width: computed.width || rect.width+'px', height: computed.height || rect.height+'px'}},
    rules, inherited,
    font: {used_family: candidates[0] || family, computed_family: family, embedded, status: fontStatus, fallbacks: candidates.slice(1)},
    limitations: Array.from(limitations)
  };
})
"""
