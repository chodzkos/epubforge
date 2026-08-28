"""Skrypt ApplicationWorld zbierający rzeczywistą kaskadę wybranego elementu."""

from epubforge.gui.css_inspector_limits import (
    MAX_CSS_ELEMENT_REPORT_DECLARATIONS,
    MAX_CSS_ELEMENT_REPORT_LIMITATIONS,
    MAX_CSS_ELEMENT_REPORT_METADATA_ITEMS,
    MAX_CSS_ELEMENT_REPORT_PATH_DEPTH,
    MAX_CSS_ELEMENT_REPORT_RULES,
    MAX_CSS_ELEMENT_REPORT_TEXT_CHARS,
    MAX_CSS_ELEMENT_REPORT_TOTAL_ITEMS,
    MAX_CSS_ELEMENT_REPORT_TOTAL_TEXT_CHARS,
    MAX_CSS_ELEMENT_RULE_DECLARATIONS,
    MAX_CSS_ELEMENT_SCAN_RULES,
)

# CSSOM i getComputedStyle pozostają źródłem prawdy. Skrypt tylko opisuje wynik
# Chromium oraz podstawową kolejność kaskady autora potrzebną do wyjaśnienia v1.
_INSPECT_SCRIPT_TEMPLATE = r"""
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
  const maxRules = __MAX_RULES__, maxScannedRules = __MAX_SCANNED_RULES__, maxDeclarations = __MAX_DECLARATIONS__, maxRuleDeclarations = __MAX_RULE_DECLARATIONS__;
  const maxMetadataItems = __MAX_METADATA_ITEMS__, maxLimitations = __MAX_LIMITATIONS__, maxPathDepth = __MAX_PATH_DEPTH__, maxTextChars = __MAX_TEXT_CHARS__;
  const maxReportTextChars = __MAX_REPORT_TEXT_CHARS__, maxReportItems = __MAX_REPORT_ITEMS__;
  let reportDeclarations = 0, scannedRules = 0, scannedSheets = 0, reportTextChars = 0, reportItems = 0, truncated = false, inspectionAborted = false;
  const jsonEscapedTextChars = value => Math.max(0, JSON.stringify(String(value ?? '')).length - 2);
  const reserveReportText = value => {
    const escapedChars = jsonEscapedTextChars(value);
    if (reportTextChars + escapedChars > maxReportTextChars) {
      truncated = true; inspectionAborted = true; return false;
    }
    reportTextChars += escapedChars;
    return true;
  };
  const reserveReportItem = (count = 1) => {
    if (reportItems + count > maxReportItems) {
      truncated = true; inspectionAborted = true; return false;
    }
    reportItems += count;
    return true;
  };
  const reportBudgetCheckpoint = () => [reportTextChars, reportItems];
  const rollbackReportBudget = checkpoint => {
    reportTextChars = checkpoint[0]; reportItems = checkpoint[1];
  };
  reserveReportItem(16);  // stały szkielet raportu i box modelu
  const boundedText = value => {
    const text = String(value ?? '');
    if (text.length > maxTextChars) truncated = true;
    const bounded = text.slice(0, maxTextChars);
    return reserveReportText(bounded) ? bounded : '';
  };
  const boundedList = (values, mapper = boundedText) => {
    const result = [];
    for (const value of values || []) {
      if (result.length >= maxMetadataItems) { truncated = true; break; }
      const mapped = mapper(value);
      if (inspectionAborted || !reserveReportItem()) break;
      result.push(mapped);
    }
    return result;
  };
  const boundedElementText = root => {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let result = '', scannedNodes = 0;
    while (result.length <= maxTextChars) {
      const node = walker.nextNode();
      if (!node) break;
      if (++scannedNodes > maxScannedRules) { truncated = true; break; }
      result += String(node.nodeValue || '').slice(0, maxTextChars + 1 - result.length);
    }
    return boundedText(result.trim().replace(/\s+/g, ' '));
  };
  const classSuffix = node => {
    let result = '', count = 0;
    for (const name of node.classList || []) {
      if (count++ >= 3) break;
      result += '.' + boundedText(name);
    }
    return result;
  };
  const limitations = new Set();
  const addLimitation = text => {
    if (limitations.size >= maxLimitations) { truncated = true; return; }
    const bounded = boundedText(text);
    if (inspectionAborted || !reserveReportItem()) return;
    limitations.add(bounded);
  };
  [
    'Pseudoelementy, animacje i transitions są tylko do odczytu.',
    '@layer, @container, @scope oraz złożone var() mają ograniczoną analizę.',
    'Pełne drzewo stylów user-agent nie jest prezentowane.',
    'Shorthandy bez jednoznacznego spanu deklaracji są edytowane wyłącznie w obrębie całej reguły.',
    'Font użyty dla konkretnego glifu nie jest ujawniany przez WebEngine; pokazano rodzinę computed i fallbacki.',
    'Łączny raport WebEngine ma budżet 1 MiB tekstu JSON; osiągnięcie limitu przerywa zbieranie kaskady.'
  ].forEach(addLimitation);
  const addLimitationValue = (prefix, value, suffix = '') => {
    const text = String(value ?? '');
    const remaining = Math.max(0, maxTextChars - prefix.length - suffix.length);
    if (text.length > remaining) truncated = true;
    addLimitation(prefix + text.slice(0, remaining) + suffix);
  };
  const propertyKey = Symbol('epubforgePropertyKey');
  let sourceOrder = 0;
  const pathFromHref = href => {
    const text = String(href ?? '');
    if (text.length > maxTextChars) { truncated = true; return null; }
    try { const url = new URL(text); return decodeURIComponent(url.pathname.replace(/^\//, '')); }
    catch (_) { return null; }
  };
  const walk = (ruleList, sheetPath, path, contexts) => {
    for (let index = 0; index < ruleList.length && !inspectionAborted; index++) {
      const rule = ruleList[index];
      if (++scannedRules > maxScannedRules) {
        truncated = true; inspectionAborted = true;
        addLimitation('Inspektor przerwał analizę po osiągnięciu limitu skanowanych reguł.');
        return;
      }
      const rulePath = path.concat(index);
      if (rulePath.length > maxPathDepth || contexts.length > maxMetadataItems) {
        truncated = true; inspectionAborted = true;
        addLimitation('Inspektor przerwał analizę zbyt głęboko zagnieżdżonych reguł.');
        return;
      }
      const type = String(rule.constructor && rule.constructor.name || 'CSSRule');
      if (rule instanceof CSSStyleRule) {
        const metadataUnsafe = rule.selectorText.length > maxTextChars ||
          (sheetPath !== null && sheetPath !== undefined && String(sheetPath).length > maxTextChars) ||
          contexts.some(ctx => String(ctx.type || '').length > maxTextChars || String(ctx.condition || '').length > maxTextChars);
        if (metadataUnsafe) {
          truncated = true; inspectionAborted = true;
          addLimitation('Inspektor przerwał analizę reguły z metadanymi przekraczającymi limit tekstu.');
          return;
        }
        let matched = false;
        try { matched = element.matches(rule.selectorText); } catch (_) { addLimitation('Nierozpoznany selektor: ' + rule.selectorText); }
        if (/:(is|not|has|where)\(/.test(rule.selectorText)) addLimitation('Specyficzność złożonych pseudoklas funkcyjnych jest przybliżona: ' + rule.selectorText);
        const order = sourceOrder++;
        if (!matched) continue;
        if (rules.length >= maxRules || rule.style.length > maxRuleDeclarations || reportDeclarations + rule.style.length > maxDeclarations) {
          truncated = true; inspectionAborted = true;
          addLimitation('Inspektor przerwał analizę po osiągnięciu limitu raportu kaskady.');
          return;
        }
        const ruleBudget = reportBudgetCheckpoint();
        const rawDeclarations = [];
        for (let i = 0; i < rule.style.length; i++) {
          const property = rule.style[i];
          const declared = rule.style.getPropertyValue(property).trim();
          const computedValue = computed.getPropertyValue(property).trim();
          if (property.length > maxTextChars || declared.length > maxTextChars || computedValue.length > maxTextChars) {
            truncated = true; inspectionAborted = true;
            addLimitation('Inspektor przerwał analizę deklaracji przekraczającej limit tekstu.');
            return;
          }
          const boundedProperty = boundedText(property);
          const boundedDeclared = boundedText(declared);
          const boundedComputed = boundedText(computedValue);
          if (inspectionAborted) { rollbackReportBudget(ruleBudget); return; }
          if (!reserveReportItem()) { rollbackReportBudget(ruleBudget); return; }
          rawDeclarations.push({property, boundedProperty, boundedDeclared, boundedComputed});
        }
        const active = contextsActive(contexts);
        const spec = bestSpecificity(rule.selectorText);
        if (!reserveReportItem(1 + rulePath.length + spec.length)) {
          rollbackReportBudget(ruleBudget); return;
        }
        const record = {
          selector: boundedText(rule.selectorText),
          stylesheet_path: sheetPath === null || sheetPath === undefined ? null : boundedText(sheetPath),
          rule_path: rulePath,
          contexts: boundedList(contexts, ctx => ({type: boundedText(ctx.type), condition: boundedText(ctx.condition)})),
          active, matched: true, specificity: spec, order, declarations: []
        };
        if (inspectionAborted) { rollbackReportBudget(ruleBudget); return; }
        for (const rawDeclaration of rawDeclarations) {
          const decl = {
            property: rawDeclaration.boundedProperty, [propertyKey]: rawDeclaration.property, declared: rawDeclaration.boundedDeclared,
            important: rule.style.getPropertyPriority(rawDeclaration.property) === 'important',
            computed: rawDeclaration.boundedComputed, active, matched: true,
            specificity: spec, order, inline: false
          };
          record.declarations.push(decl);
          declarations.push(decl);
        }
        rules.push(record);
        reportDeclarations += record.declarations.length;
      } else if (rule.type === CSSRule.IMPORT_RULE && rule.styleSheet) {
        const importedPath = pathFromHref(rule.href);
        const importedContexts = rule.media && rule.media.mediaText ? contexts.concat({type:'media', condition:rule.media.mediaText}) : contexts;
        try { walk(rule.styleSheet.cssRules, importedPath, [], importedContexts); }
        catch (_) { addLimitationValue('Nie odczytano importowanego arkusza: ', importedPath || rule.href); }
      } else if (rule.cssRules) {
        let context = {type: type.replace(/^CSS|Rule$/g, '').toLowerCase(), condition: rule.conditionText || rule.name || ''};
        if (rule instanceof CSSMediaRule) context.type = 'media';
        else if (typeof CSSSupportsRule !== 'undefined' && rule instanceof CSSSupportsRule) context.type = 'supports';
        else if (!['media','supports'].includes(context.type)) addLimitation('Ograniczona analiza ' + type + '.');
        walk(rule.cssRules, sheetPath, rulePath, contexts.concat(context));
      } else if (![CSSRule.FONT_FACE_RULE, CSSRule.IMPORT_RULE].includes(rule.type)) {
        addLimitation('Nierozpoznana reguła CSSOM: ' + type + '.');
      }
    }
  };
  for (const sheet of document.styleSheets) {
    if (inspectionAborted) break;
    if (++scannedSheets > maxScannedRules) {
      truncated = true; inspectionAborted = true;
      addLimitation('Inspektor przerwał analizę po osiągnięciu limitu arkuszy.');
      break;
    }
    const owner = sheet.ownerNode;
    if (owner && owner.id && owner.id.startsWith('epubforge-') && owner.id !== 'epubforge-css-preview-layer') continue;
    const path = owner && owner.dataset ? (owner.dataset.epubforgePath || null) : null;
    try { walk(sheet.cssRules, path, [], []); }
    catch (_) { addLimitationValue('Arkusz niedostępny dla CSSOM: ', path || 'inline', '.'); }
  }
  if (!inspectionAborted && element.style.length) {
    if (rules.length >= maxRules || element.style.length > maxRuleDeclarations || reportDeclarations + element.style.length > maxDeclarations) {
      truncated = true; inspectionAborted = true;
      addLimitation('Inspektor przerwał analizę po osiągnięciu limitu stylu inline.');
    } else {
      const inlineBudget = reportBudgetCheckpoint();
      const rawInlineDeclarations = [];
      for (let i = 0; i < element.style.length; i++) {
        const property = element.style[i];
        const declared = element.style.getPropertyValue(property).trim();
        const computedValue = computed.getPropertyValue(property).trim();
        if (property.length > maxTextChars || declared.length > maxTextChars || computedValue.length > maxTextChars) {
          truncated = true; inspectionAborted = true;
          addLimitation('Inspektor przerwał analizę deklaracji inline przekraczającej limit tekstu.');
          break;
        }
        const boundedProperty = boundedText(property);
        const boundedDeclared = boundedText(declared);
        const boundedComputed = boundedText(computedValue);
        if (inspectionAborted || !reserveReportItem()) {
          rollbackReportBudget(inlineBudget); break;
        }
        rawInlineDeclarations.push({property, boundedProperty, boundedDeclared, boundedComputed});
      }
      if (!inspectionAborted && reserveReportItem(6)) {
        const inlineRule = {selector: boundedText('element.style'), stylesheet_path: null, rule_path: ['inline'], contexts: [], active: true, matched: true, specificity: [1,0,0,0], order: sourceOrder++, declarations: []};
        for (const rawDeclaration of rawInlineDeclarations) {
          const decl = {property: rawDeclaration.boundedProperty, [propertyKey]: rawDeclaration.property, declared: rawDeclaration.boundedDeclared, important: element.style.getPropertyPriority(rawDeclaration.property) === 'important', computed: rawDeclaration.boundedComputed, active: true, matched: true, specificity: [1,0,0,0], order: inlineRule.order, inline: true};
          inlineRule.declarations.push(decl); declarations.push(decl);
        }
        rules.push(inlineRule); reportDeclarations += inlineRule.declarations.length;
      } else if (inspectionAborted) {
        rollbackReportBudget(inlineBudget);
      }
    }
  }
  if (inspectionAborted) {
    rules.length = 0;
    declarations.length = 0;
    reportDeclarations = 0;
  }

  // Klasyfikacja wyłącznie podstawowej kaskady v1; computed value nadal pochodzi z Chromium.
  const byProperty = new Map();
  const winners = new Map();
  declarations.forEach(d => {
    const key = d[propertyKey] || d.property;
    if (d.active && d.matched) (byProperty.get(key) || byProperty.set(key, []).get(key)).push(d);
  });
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
    if (!byProperty.has(property) && computed.getPropertyValue(property) === parentComputed.getPropertyValue(property)) {
      const item = {property: boundedText(property), computed: boundedText(computed.getPropertyValue(property).trim()), from: boundedText(element.parentElement.localName)};
      if (!inspectionAborted && reserveReportItem()) inherited.push(item);
    }
  });
  const rect = element.getBoundingClientRect();
  const side = (prefix, name) => ({top: boundedText(computed.getPropertyValue(prefix+'-top'+name)), right: boundedText(computed.getPropertyValue(prefix+'-right'+name)), bottom: boundedText(computed.getPropertyValue(prefix+'-bottom'+name)), left: boundedText(computed.getPropertyValue(prefix+'-left'+name))});
  const breadcrumb = [];
  for (let n = element; n && n.nodeType === 1 && breadcrumb.length < maxMetadataItems; n = n.parentElement) {
    const name = boundedText(n.localName);
    const id = n.id ? '#' + boundedText(n.id) : '';
    const crumb = boundedText(name + id + classSuffix(n));
    if (inspectionAborted || !reserveReportItem()) break;
    breadcrumb.unshift(crumb);
    if (breadcrumb.length === maxMetadataItems && n.parentElement) truncated = true;
  }
  const family = boundedText(computed.fontFamily);
  const candidates = family.split(',', maxMetadataItems + 1).map(x => boundedText(x.trim().replace(/^['"]|['"]$/g, ''))).filter(Boolean);
  if (candidates.length > maxMetadataItems) { candidates.length = maxMetadataItems; truncated = true; }
  if (!inspectionAborted && !reserveReportItem(candidates.length)) candidates.length = 0;
  let embedded = false, fontStatus = 'font systemowy lub fallback';
  if (document.fonts) {
    let faceCount = 0;
    const statuses = [];
    let scannedFaces = 0, statusChars = 0;
    for (const face of document.fonts) {
      if (++scannedFaces > maxScannedRules) { truncated = true; break; }
      const faceFamily = String(face.family || '');
      if (faceFamily.length > maxTextChars) { truncated = true; continue; }
      if (faceFamily.replace(/^['"]|['"]$/g, '') !== (candidates[0] || '')) continue;
      faceCount++;
      const status = boundedText(face.status);
      if (faceCount <= maxMetadataItems && statusChars + status.length <= maxTextChars && !inspectionAborted && reserveReportItem()) {
        statuses.push(status); statusChars += status.length;
      } else truncated = true;
      if (face.status === 'loaded') embedded = true;
    }
    if (faceCount) fontStatus = embedded ? 'osadzony, gotowy' : statuses.join(', ');
  }
  const result = {
    available: true, node_id: boundedText(element.getAttribute('data-epubforge-node-id')), breadcrumb,
    element: {tag: boundedText(element.localName), id: boundedText(element.id || ''), classes: boundedList(element.classList), text: boundedElementText(element).slice(0,160)},
    box: {margin: side('margin',''), border: side('border','-width'), padding: side('padding',''), content: {width: boundedText(computed.width || rect.width+'px'), height: boundedText(computed.height || rect.height+'px')}},
    rules, inherited: inherited.slice(0, maxMetadataItems), truncated: false, cascade_truncated: false,
    font: {used_family: boundedText(candidates[0] || family), computed_family: boundedText(family), embedded, status: boundedText(fontStatus), fallbacks: candidates.slice(1, maxMetadataItems)},
    limitations: Array.from(limitations).slice(0, maxLimitations)
  };
  if (inspectionAborted) {
    rules.length = 0;
    declarations.length = 0;
    inherited.length = 0;
    result.rules = [];
    result.inherited = [];
  }
  result.truncated = truncated;
  result.cascade_truncated = inspectionAborted;
  return result;
})
"""

INSPECT_SCRIPT = (
    _INSPECT_SCRIPT_TEMPLATE.replace("__MAX_RULES__", str(MAX_CSS_ELEMENT_REPORT_RULES))
    .replace("__MAX_SCANNED_RULES__", str(MAX_CSS_ELEMENT_SCAN_RULES))
    .replace("__MAX_DECLARATIONS__", str(MAX_CSS_ELEMENT_REPORT_DECLARATIONS))
    .replace("__MAX_RULE_DECLARATIONS__", str(MAX_CSS_ELEMENT_RULE_DECLARATIONS))
    .replace("__MAX_METADATA_ITEMS__", str(MAX_CSS_ELEMENT_REPORT_METADATA_ITEMS))
    .replace("__MAX_LIMITATIONS__", str(MAX_CSS_ELEMENT_REPORT_LIMITATIONS))
    .replace("__MAX_PATH_DEPTH__", str(MAX_CSS_ELEMENT_REPORT_PATH_DEPTH))
    .replace("__MAX_TEXT_CHARS__", str(MAX_CSS_ELEMENT_REPORT_TEXT_CHARS))
    .replace("__MAX_REPORT_TEXT_CHARS__", str(MAX_CSS_ELEMENT_REPORT_TOTAL_TEXT_CHARS))
    .replace("__MAX_REPORT_ITEMS__", str(MAX_CSS_ELEMENT_REPORT_TOTAL_ITEMS))
)
