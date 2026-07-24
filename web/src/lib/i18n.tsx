"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

export type Lang = "en" | "ko";

const LANG_KEY = "markettrace_lang";

type Dict = { [key: string]: string | Dict };

const en: Dict = {
  nav: {
    search: "Search",
    recommendations: "Picks",
    events: "Events",
    rankings: "Rankings",
    screener: "Drops",
    stats: "Stats",
    macro: "Macro",
    ledger: "Ledger",
    passbook: "Passbook",
    alerts: "Alerts",
    watchlist: "Watchlist",
    admin: "Admin",
  },
  recommendations: {
    title: "Recommended Stocks",
    subtitle:
      "Sharp-drop stocks sorted by which deserve review first. The order combines recent price moves, recent company events, and how similar past events played out.",
    disclaimer:
      "This is a review list, not a promise that the stock will rise. Open each stock, read the reasons, and check fresh news before making any decision.",
    loading: "Loading recommendations...",
    failTitle: "Failed to load recommendations.",
    empty:
      "No fresh sharp-drop stocks match the rule right now. Refresh recent prices and try again.",
    sourceNote:
      "Rule: if any stock is down at least 15% from its recent high, show every such stock; otherwise show the 5 biggest relative drops.",
    viewStock: "Open stock",
    priceLabel: "Current / recent high",
    asOf: "price date {date}",
    recentEvents: "{count} recent event(s)",
    noRecentEvents: "No recent events found",
    level: {
      first_pick: "Review first",
      check: "Needs checking",
      avoid: "Low priority",
    },
    section: {
      domestic: "Domestic",
      domesticDesc: "Korean-market sharp-drop stocks.",
      domesticEmpty: "No domestic sharp-drop stocks match the rule right now.",
      overseas: "Overseas",
      overseasDesc: "US and other overseas sharp-drop stocks.",
      overseasEmpty: "No overseas sharp-drop stocks match the rule right now.",
      count: "{count} stocks",
      trueDropMode: "Showing every stock down at least 15% from its recent high.",
      relativeMode:
        "No stock is down 15% or more here, so this shows the 5 largest relative drops.",
    },
    reasonTitle: "Why this appears here",
    reason: {
      deepDrop:
        "The stock is {drop}% below its recent high, so the price has already fallen a lot.",
      relativeDrop:
        "The stock is {drop}% below its recent high. This is not necessarily a major crash, but it is one of the larger drops in the current list.",
      freshPrice:
        "The price data is recent enough to use for today's review.",
      stalePrice:
        "The latest price is old, so this should be checked again before acting.",
      possibleOverreaction:
        "There is recent company news, but our records do not show a strong pattern that this type of news keeps hurting the stock.",
      unexplained:
        "We do not see a clear recent company event explaining the fall, so the first job is to find what caused it.",
      persistentRisk:
        "Recent company news looks similar to past cases where investors stayed cautious, so this is ranked lower.",
      recentEvents:
        "{count} recent company event(s) were found, so this is not based on price alone.",
      factorBad:
        "Main caution point: {label}. Similar news has often made investors careful.",
      factorGood:
        "Helpful point: {label}. Similar news has often been received better.",
    },
  },
  common: { unknownError: "Unknown error" },
  search: {
    title: "Search instruments",
    subtitle:
      "Find a stock by ticker, name, or alias. If it is not in Events yet, run filing analysis by company name.",
    placeholder: "Ticker, company name, or alias…",
    searching: "Searching…",
    noResults: "No instruments match “{q}”.",
    hint: "Type at least one character to search.",
    eventsCount: "{count} events",
    noEvents: "no events yet",
    tickerLabel: "Ticker (optional)",
    nameLabel: "Company name",
    namePlaceholder: "Optional",
    analyzeButton: "Analyze filings",
    analyzing: "Starting…",
    analyzeStarted:
      "{ticker} analysis started. New events will appear after extraction finishes.",
    analyzeFailed: "Analysis request failed.",
    loginRequired: "Log in to run analysis.",
    sessionExpired: "Session expired. Please log in again, then run analysis.",
    noListedCompany:
      "No matching listed KR/US company was found. Private companies such as SpaceX are not supported.",
    providerUnavailable:
      "The disclosure provider is not configured for this market.",
  },
  screener: {
    title: "Sharp drops",
    subtitle:
      "Stocks down hard from their 20-day high, each diagnosed against validated event history.",
    disclaimer:
      "This is a diagnosis, not a buy call. This system has no validated bullish signal — every validated event type drifts negative — so it never asserts a stock will rise. “Possible overreaction” flags a rebound candidate pending backtest validation only.",
    loading: "Loading…",
    failTitle: "Failed to load the screener.",
    empty: "No instruments are down past the threshold with fresh prices.",
    thresholdLabel: "Min drop",
    includeStale: "Include stale prices",
    staleTag: "stale",
    col: {
      instrument: "Instrument",
      drawdown: "Drawdown",
      priceRange: "Now / 20d high",
      diagnosis: "Diagnosis",
      recentEvents: "Recent events",
      lean: "Validated lean",
      topFactor: "Top factor",
    },
    diagnosis: {
      persistent_risk: "Persistent risk",
      unexplained_drop: "Unexplained drop",
      possible_overreaction: "Possible overreaction",
      persistent_riskDesc:
        "Recent event(s) and a validated-negative lean — the fall is consistent with this name’s history; caution likely continues.",
      unexplained_dropDesc:
        "No recent events in our data explain this fall. An observation, not a signal — we have no event basis.",
      possible_overreactionDesc:
        "Recent event(s) but no validated-negative basis. A rebound candidate pending backtest validation — not a buy call.",
    },
    asOf: "as of {date}",
    eventsInWindow: "{count} in 30d",
    noLean: "—",
    rebound: {
      title: "Rebound backtest",
      subtitle:
        "Does buying after such a drop pay off? Fixed rule, out-of-sample, net of costs.",
      insufficient:
        "Not enough clean price history to validate a rebound edge yet — refresh recent prices to build it. Until then “possible overreaction” stays an observation, not a signal.",
      marketAdjusted: "market-adjusted",
      raw: "raw (no benchmark)",
      colHorizon: "Horizon",
      colSignals: "Signals",
      colHitRate: "Hit rate",
      colNet: "Mean net return",
      days: "{n}d",
      coverage: "{scored} scored / {dropped} no outcome",
    },
  },
  watchlist: {
    title: "Watchlist",
    subtitle: "Instruments you watch for alerts",
    empty: "Your watchlist is empty.",
    howToAdd: "Add instruments with the ☆ button on the Events list or an instrument page.",
    events: "Events",
  },
  alerts: {
    title: "Alerts",
    subtitle: "Notable events on your watched instruments",
    empty: "No alerts yet. Watch an instrument to be notified of its notable events.",
    markAllRead: "Mark all read",
    groupCount: "{count} alerts",
    conflictDesc: "Model direction conflicts with the validated historical drift",
    significantDesc: "Validated significant event type",
    kindConflict: "Conflict",
    kindSignificant: "Significant",
  },
  watch: {
    watch: "Watch",
    watching: "Watching",
    loginToWatch: "Log in to watch",
    sessionExpired: "Session expired — log in again",
  },
  auth: {
    login: "Login",
    logout: "Logout",
    signInTitle: "Sign in",
    signIn: "Sign in",
    signingIn: "Signing in…",
    cancel: "Cancel",
    username: "Username",
    password: "Password",
    invalidCreds: "Invalid username or password.",
    loginFailed: "Login failed",
  },
  ingest: {
    button: "Ingest data",
    starting: "Starting…",
    ingesting: "Ingesting… (~1–2 min)",
    started: "Ingestion started — data will appear shortly",
    sessionExpired: "Session expired — please log in again.",
    errorPrefix: "Error: ",
    failed: "Ingest failed",
    refresh: "Refresh",
    eventsLoaded: "✓ {n} events loaded",
    inProgress: "Ingestion in progress — refresh to check for new data",
  },
  events: {
    loading: "Loading events...",
    failTitle: "Failed to load events",
    backendHint: "Make sure the backend is running at {url}",
    title: "Market Events",
    count: "{n} events",
    empty: "No events found. Run the pipeline to ingest disclosures.",
    th: {
      ticker: "Ticker",
      instrument: "Instrument",
      eventType: "Event Type",
      direction: "Direction",
      confidence: "Confidence",
      published: "Published",
    },
    tab: {
      domestic: "Domestic (KR)",
      overseas: "Overseas (US)",
    },
    companyEvents: "{n} events",
    noneInMarket: "No events in this market.",
    expandHint: "Select a company to see its events, latest first.",
    searchLabel: "Search events",
    searchPlaceholder: "Search ticker, company, event type, or direction...",
    searchHint: "Search filters the selected market and signal view.",
    searchCount: "{n} matching events",
    signalFilter: {
      all: "All",
      conflict: "Conflicts only",
      needsReview: "Needs review",
      validated: "Validated only",
    },
    reviewedMark: "Reviewed",
    noneSearchResults: "No events match this search.",
    noneMatchFilter: "No events match this filter.",
    tip: {
      confidence:
        "Confidence — how sure the model is about its read (direction/type) of this event. Closer to 100% means higher self-assessed conviction; it is not a guarantee of the actual return.",
      signal:
        "Signal — how this event type has actually moved the market historically, from validated statistics (n≥5, p<0.05). It compares the model's read against that history. No badge means there is no validated signal for this type yet.",
    },
  },
  stats: {
    loading: "Loading statistics...",
    failTitle: "Failed to load statistics",
    title: "Event-Type Reaction Stats",
    buckets: "{n} buckets",
    subtitle:
      "Mean and dispersion of market-adjusted abnormal returns, grouped by event type and post-announcement horizon (trading days).",
    empty: "No statistics yet — ingest some events first.",
    howToRead: "How to read this",
    howToReadBody:
      "Each row is one event type. Each cell is the average move of the stock, relative to the market, over the N trading days after that type of filing — green is up, red is down, and n is how many filings it averages. Click a cell to see the actual filings behind that number.",
    th: {
      eventType: "Event Type",
      horizon: "Horizon",
      samples: "Samples",
      total: "Samples",
      horizonGroup: "Trading days after filing",
      mean: "Mean Abnormal Return",
      std: "Std Dev",
    },
    noData: "no data",
    relatedHint:
      "Select a cell to see the exact filings its average is computed over — each with its own abnormal return.",
    relatedTitle: "Events behind {type} · D+{horizon}",
    relatedCount: "{n} events",
    relatedSummary: "Mean of these {n} = {mean}",
    relatedReturn: "Abnormal Return",
    relatedEmpty: "No matching events.",
    signals: {
      title: "Validated Signals",
      subtitle:
        "Event types whose average abnormal return is both backed by enough samples (n≥5) and statistically distinguishable from zero (p<0.05). These are the reactions the data actually supports — everything else is noise.",
      count: "{n} significant",
      empty:
        "No statistically significant signals yet — the samples aren't conclusive. Ingest more events to build power.",
      negativeNote:
        "Every validated signal so far is negative: these filings precede a market-relative decline, so they read as caution / avoid rather than buy signals.",
      badge: "significant",
      th: {
        eventType: "Event Type",
        horizon: "Horizon",
        mean: "Mean Abnormal",
        t: "t-stat",
        p: "p-value",
        n: "n",
      },
    },
    backtest: {
      title: "Walk-Forward Backtest",
      subtitle:
        "Out-of-sample signal performance per horizon, net of trading costs (look-ahead blocked).",
      modelLabel: "Signal model",
      model: {
        event_type_history: "Event-type history",
        significant_event_type: "Significant only",
        macro_surprise: "Macro regime",
        price_momentum: "Price momentum",
        combined: "Combined",
        llm_direction: "LLM direction",
      },
      loading: "Loading backtest...",
      failTitle: "Failed to load backtest",
      empty: "No backtest results yet — ingest some events first.",
      th: {
        horizon: "Horizon",
        predictions: "Predictions",
        hitRate: "Hit Rate",
        gross: "Gross Return",
        net: "Net Return",
        ic: "IC",
        coverage: "Coverage",
      },
      coverageHint: "used / dropped (no outcome)",
    },
    macro: {
      title: "Macro Regime Decomposition",
      subtitle:
        "The macro-regime signal backtested on each series alone. If the edge concentrates in one economically meaningful series it argues for real macro content; if every series looks alike it's likely a slow calendar/regime proxy.",
      loading: "Loading macro decomposition...",
      failTitle: "Failed to load macro decomposition",
      empty: "No macro series with surprises yet.",
      th: {
        series: "Macro Series",
        icGroup: "Information coefficient by horizon",
        net: "Net return",
      },
      readHint:
        "Each cell is the out-of-sample information coefficient (predicted vs realised correlation) of conditioning on that series' surprise sign; hover for net-of-cost return and sample size. Green = positive predictive correlation.",
    },
    calibration: {
      title: "Confidence Calibration",
      subtitle:
        "Does a confidence of 0.7 actually hit ~70%? Directional calls binned by their stated confidence, per horizon, with the observed hit rate against the model's confidence.",
      horizonLabel: "Horizon",
      loading: "Loading calibration...",
      failTitle: "Failed to load calibration",
      empty: "Not enough directional predictions to calibrate yet.",
      summary:
        "{n} directional predictions · mean confidence {conf} vs actual hit rate {hit}",
      ece: "Calibration error (ECE)",
      brier: "Brier score",
      verdict: {
        over: "Overconfident — stated confidence runs ahead of actual accuracy.",
        under: "Underconfident — actual accuracy beats stated confidence.",
        good: "Well calibrated — stated confidence tracks actual accuracy.",
      },
      th: {
        band: "Confidence band",
        n: "n",
        meanConf: "Mean confidence",
        hitRate: "Actual hit rate",
        gap: "Gap",
      },
      readHint:
        "Gap = mean confidence − actual hit rate. Positive (amber) = overconfident in that band; negative (green) = underconfident. Neutral calls and events with no realised return are excluded. ECE is the sample-weighted average gap; Brier is the mean squared error of confidence vs outcome (lower is better).",
    },
  },
  eventDetail: {
    loading: "Loading event...",
    failTitle: "Failed to load event",
    unknownInstrument: "Unknown Instrument",
    model: "Model",
    version: "Version",
    sourceDoc: "Source Document",
    evidence: "Supporting Evidence",
    industries: "Industries",
    channels: "Channels",
    signal: {
      title: "Validated Signal",
      subtitle:
        "How this event type has actually moved the market historically — and whether that agrees with the model's read.",
      verdictLabel: "Model vs. history",
      conflict:
        "Conflict — the model reads {llm}, but validated history for this event type points {hist}.",
      agree:
        "Agreement — the model's {llm} read matches validated history ({hist}).",
      info:
        "The model reads neutral; validated history for this event type points {hist}.",
      none:
        "No statistically significant signal for this event type yet (n≥5, p<0.05). Treat the model's read as unconfirmed.",
      up: "up",
      down: "down",
      short: {
        conflict: "Conflict",
        conflictTitle: "Model read conflicts with validated history",
        agree: "Confirmed",
        agreeTitle: "Model read matches validated history",
        info: "Signal",
        infoTitle: "Validated signal exists; model is neutral",
      },
      badge: {
        conflict:
          "Conflict — the model's direction is the opposite of this event type's validated history (a statistically significant move, n≥5, p<0.05). Worth a second look.",
        agree:
          "Confirmed — the model's direction matches this event type's validated historical drift.",
        info:
          "Signal — this event type has a statistically significant historical direction (n≥5, p<0.05), but the model read it as neutral. Lean on the historical direction.",
      },
    },
    review: {
      title: "Review & correct",
      subtitle:
        "Correct the model's read. Direction/type edits update stats immediately; company edits recompute returns for the corrected instrument.",
      direction: "Direction",
      eventType: "Event type",
      company: "Company",
      confidence: "Confidence",
      recomputeNote:
        "Changing the company will refetch prices and recompute outcomes for this event.",
      save: "Save",
      saving: "Saving…",
      noChanges: "No changes",
      failed: "Save failed. Try again.",
      recomputeFailed:
        "Company correction failed while recomputing prices. No changes were saved.",
      sessionExpired: "Session expired — please log in again.",
      reviewedAt: "Human-reviewed on {date}",
    },
  },
  instrument: {
    loading: "Loading instrument timeline...",
    failTitle: "Failed to load instrument",
    timeline: "Event Timeline",
    eventsCount: "({n} events)",
    empty: "No events recorded for this instrument.",
    conf: "conf",
    signal: {
      title: "Signal summary",
      subtitle:
        "What has historically followed this stock's kind of news, from validated event-type drift. Not a price prediction.",
      basis: "from {n} validated events",
      none: "No events with a validated signal yet for this stock.",
      netDrift: "Avg validated drift",
      validatedEvents: "Validated events",
      conflicts: "Conflicts (unreviewed)",
      lean: {
        bearish: "Caution — validated history leans to the downside.",
        bullish: "Constructive — validated history leans to the upside.",
        neutral: "Mixed — no clear validated lean.",
        none: "Insufficient validated signal.",
      },
    },
    factors: {
      title: "Upside vs. downside factors",
      subtitle:
        "The event types in this stock's history that carry a validated drift — what could move it, and which way.",
      upside: "Upside factors",
      downside: "Downside factors",
      none: "None identified.",
      detail: "D+{horizon} · {count}× · latest {date}",
    },
  },
  rankings: {
    title: "Instrument Rankings",
    subtitle:
      "Every instrument ranked by its confidence- and recency-weighted validated drift — a cross-stock buy-judgment view. Recent, high-confidence events count more than stale, low-confidence ones. Not a price prediction; strongest historical caution first.",
    loading: "Loading rankings...",
    failTitle: "Failed to load rankings",
    empty:
      "No instruments have enough validated events to rank yet. Ingest more events to build power.",
    weightingNote:
      "Weighting: each validated event × its LLM confidence × recency (half-life {halfLife} days).",
    col: {
      rank: "#",
      instrument: "Instrument",
      lean: "Lean",
      score: "Weighted drift",
      simpleMean: "Simple mean",
      validated: "Validated",
      conflicts: "Conflicts",
      topFactor: "Top factor",
    },
    lean: { bearish: "Caution", bullish: "Favorable", neutral: "Mixed" },
    factor: "{label} {drift} ({count}×)",
    conflictsCell: "{total} ({unreviewed} unreviewed)",
    tip: {
      lean:
        "Lean — this instrument's overall direction from its validated history: Caution (downside), Favorable (upside), or Mixed (no clear direction).",
      score:
        "Weighted drift — the post-event average return (drift) of this instrument's validated events, summed with each event weighted by the model's confidence and by recency (recent events count more). This is what the ranking is sorted by.",
      simpleMean:
        "Simple mean — the same validated events' drift averaged with no weighting. Compare it against the weighted drift to see how much the confidence/recency weighting changed the picture.",
      validated:
        "Validated — the number of this instrument's events that carry a statistically significant signal (n≥5, p<0.05).",
      conflicts:
        "Conflicts — events where the model's direction is the opposite of validated history. The number in parentheses is how many of those a human has not reviewed yet.",
      topFactor:
        "Top factor — the event type contributing most to the weighted drift, with its post-event average return.",
    },
  },
  direction: { positive: "positive", negative: "negative", neutral: "neutral" },
  chart: {
    title: "Abnormal Returns (%)",
    noData: "No outcome data available",
    noDataWhy:
      "Returns are only computed once a fixed number of trading days (e.g. 1 / 5 / 20 / 60) have elapsed after the filing. This chart stays empty when the event is too recent for those windows to have passed, or when price data for the instrument has not been collected yet.",
    titleTip:
      "Abnormal return — the instrument's actual return minus the market (index) return over the same window. It strips out the overall market move so you see the effect attributable to this event alone.",
    abnormalReturn: "Abnormal Return",
    rawReturn: "Raw Return",
    sectorAdjusted: "Sector-Adjusted",
    marketReturn: "Market Return",
    abnormal: "Abnormal",
    raw: "Raw",
    market: "Market",
  },
  scores: {
    title: "Score Components",
    confidence: "Confidence",
    surprise: "Surprise",
    novelty: "Novelty",
    sourceReliability: "Source Reliability",
    titleTip:
      "Each score is shown as 0–100%.\n• Confidence: how sure the model is about its read of this event.\n• Surprise: how far the news diverged from what the market expected — higher means more unexpected.\n• Novelty: how genuinely new the information is — repeated / routine filings score lower.\n• Source Reliability: how trustworthy the disclosure source is.",
  },
  macro: {
    title: "Macro Surprises",
    count: "{n} series",
    loading: "Loading macro data...",
    failTitle: "Failed to load macro data",
    subtitle:
      "This tab tracks how far economic releases (inflation, jobs, rates…) landed from what the market expected. What moves the overall market mood — the backdrop against which every stock and event trades — is not the raw number but how it differs from expectations (the surprise). Collecting those surprises in one standardized view gives you the regime context for reading sharp drops and events.",
    empty: "No macro data yet — run the macro ingest first.",
    th: {
      series: "Series",
      reference: "Reference",
      released: "Released",
      expected: "Expected",
      surprise: "Surprise (σ)",
    },
    tip: {
      released: "Released — the actual figure that was published for this indicator.",
      expected:
        "Expected — what the market anticipated before the release. Uses consensus (experts' pooled forecast) when available, otherwise a trend baseline forecast.",
      surprise:
        "Surprise (σ) — (released − expected) divided by the indicator's historical volatility (standard deviation). Positive means it came in better/higher than expected, negative means worse/lower; a bigger number means a bigger shock. The σ (sigma) unit means \"how many times the usual wobble\", so different indicators can be compared on one scale.",
    },
    baseline: "baseline",
    consensus: "consensus",
  },
  ledger: {
    title: "Card Ledger",
    subtitle: "Upload a password-protected card statement PDF to organize spend entries.",
    loginRequired: "Sign in to view the ledger.",
    fileLabel: "Statement PDF",
    fileHelp: "Select a PDF statement",
    missingFile: "Select a statement PDF first.",
    passwordLabel: "Statement password",
    passwordPlaceholder: "Enter PDF password",
    passwordRequired: "Enter the statement password.",
    invalidPassword: "The statement password is incorrect.",
    load: "Upload and parse",
    loading: "Loading ledger...",
    parsing: "Uploading and parsing statement...",
    failTitle: "Failed to load ledger",
    sessionExpired: "Session expired. Please sign in again, then upload the statement.",
    monthLabel: "Statement month",
    savedMonths: "{n} saved months",
    listLoading: "Loading saved months...",
    detailLoading: "Loading selected statement...",
    noSavedStatements: "No saved statements yet.",
    file: "File",
    uploadedAt: "Uploaded",
    statementMonth: "Statement month",
    period: "Period",
    paymentDue: "Payment due",
    billedTotal: "Billed total",
    foreignTotal: "Foreign total",
    parsedTotal: "Parsed total",
    entries: "{n} entries",
    warnings: "Warnings",
    categories: "Category totals",
    th: {
      date: "Date",
      category: "Category",
      description: "Merchant",
      card: "Card",
      amount: "Amount",
    },
    empty: "No parsed ledger entries.",
    chartTitle: "Top spending categories",
    chartSubtitle: "Top 10 categories by amount",
    windowMonth: "This month",
    windowYear: "Last 12 months",
    chartLoading: "Loading category totals...",
    chartEmpty: "No category totals to chart yet.",
    chartAmount: "Amount",
    topTitle: "Biggest spends",
    topSubtitle: "Top 10 transactions by amount (date + place)",
    topEmpty: "No transactions to rank yet.",
  },
  passbook: {
    title: "Bank Passbook",
    subtitle: "Upload a password-protected bank-account PDF to organize transactions.",
    loginRequired: "Sign in to view the passbook.",
    fileLabel: "Passbook PDF",
    fileHelp: "Select a PDF transaction export",
    missingFile: "Select a passbook PDF first.",
    passwordLabel: "PDF password",
    passwordPlaceholder: "Enter PDF password",
    passwordRequired: "Enter the PDF password.",
    invalidPassword: "The PDF password is incorrect.",
    load: "Upload and parse",
    parsing: "Uploading and parsing passbook...",
    failTitle: "Failed to load passbook",
    sessionExpired: "Session expired. Please sign in again, then upload the passbook.",
    monthLabel: "Statement month",
    savedMonths: "{n} saved months",
    listLoading: "Loading saved months...",
    detailLoading: "Loading selected statement...",
    noSavedStatements: "No saved statements yet.",
    file: "File",
    uploadedAt: "Uploaded",
    statementMonth: "Statement month",
    account: "Account",
    holder: "Holder",
    period: "Period",
    closingBalance: "Closing balance",
    withdrawalTotal: "Total out",
    depositTotal: "Total in",
    entries: "{n} transactions",
    warnings: "Warnings",
    th: {
      date: "Date",
      time: "Time",
      summary: "Type",
      description: "Counterparty",
      withdrawal: "Out",
      deposit: "In",
      balance: "Balance",
      branch: "Branch",
    },
    empty: "No parsed transactions.",
    chartTitle: "Top categories",
    chartSubtitle: "Top 10 categories by amount",
    windowMonth: "This month",
    windowYear: "Last 12 months",
    directionOut: "Withdrawals",
    directionIn: "Deposits",
    chartLoading: "Loading category totals...",
    chartEmpty: "No category totals to chart yet.",
    chartAmount: "Amount",
    topTitleOut: "Biggest withdrawals",
    topTitleIn: "Biggest deposits",
    topSubtitle: "Top 10 transactions by amount (date + counterparty)",
    topEmpty: "No transactions to rank yet.",
  },
  customize: {
    th: { category: "Category" },
    edit: "Edit",
    edited: "Edited",
    reassignTitle: "Reassign category",
    categoryLabel: "Category",
    newCategoryOption: "+ New category…",
    newCategoryPlaceholder: "New category name",
    scopeSingle: "This entry only",
    scopeRule: "All matching (save a rule)",
    keywordLabel: "Keyword",
    ruleHint: "Every entry whose merchant / memo contains this keyword is recategorized, now and in future statements.",
    categoryRequired: "Enter a category name.",
    keywordRequired: "Enter a keyword.",
    revert: "Revert to auto",
    cancel: "Cancel",
    apply: "Apply",
    managerTitle: "Manage categories",
    managerSummary: "{categories} custom · {rules} rules",
    customCategories: "Custom categories",
    add: "Add",
    deleteCategory: "Delete category {name}",
    noCustomCategories: "No custom categories yet.",
    rulesTitle: "Keyword rules",
    delete: "Delete",
    noRules: "No keyword rules yet.",
  },
};

const ko: Dict = {
  nav: {
    search: "검색",
    recommendations: "추천종목",
    events: "이벤트",
    rankings: "랭킹",
    screener: "급락",
    stats: "통계",
    macro: "거시",
    ledger: "가계부",
    passbook: "통장관리",
    alerts: "알림",
    watchlist: "관심종목",
    admin: "관리자",
  },
  recommendations: {
    title: "추천종목",
    subtitle:
      "급락 종목 중에서 먼저 살펴볼 만한 순서로 정렬했습니다. 최근 가격 흐름, 최근 회사 소식, 비슷한 소식 뒤의 과거 움직임을 함께 봅니다.",
    disclaimer:
      "이 목록은 '반드시 오른다'는 뜻이 아닙니다. 각 종목의 이유를 읽고, 최신 뉴스와 공시를 확인한 뒤 판단해야 합니다.",
    loading: "추천종목 불러오는 중...",
    failTitle: "추천종목을 불러오지 못했습니다.",
    empty:
      "현재 기준에 맞는 최신 급락 종목이 없습니다. 최근 가격을 갱신한 뒤 다시 확인하세요.",
    sourceNote:
      "기준: 최근 고점보다 15% 이상 내려온 종목이 있으면 전부 보여주고, 없으면 상대적으로 가장 많이 내려온 5개만 보여줍니다.",
    viewStock: "종목 보기",
    priceLabel: "현재가 / 최근 고점",
    asOf: "가격 기준일 {date}",
    recentEvents: "최근 사건 {count}건",
    noRecentEvents: "최근 사건 없음",
    level: {
      first_pick: "우선 검토",
      check: "추가 확인",
      avoid: "추천 낮음",
    },
    section: {
      domestic: "국내",
      domesticDesc: "국내 시장 급락 종목입니다.",
      domesticEmpty: "현재 기준에 맞는 국내 급락 종목이 없습니다.",
      overseas: "해외",
      overseasDesc: "미국 등 해외 시장 급락 종목입니다.",
      overseasEmpty: "현재 기준에 맞는 해외 급락 종목이 없습니다.",
      count: "{count}개",
      trueDropMode: "최근 고점 대비 15% 이상 내려온 종목을 전부 보여줍니다.",
      relativeMode:
        "15% 이상 급락한 종목이 없어, 현재 목록에서 상대적으로 많이 내려온 5개만 보여줍니다.",
    },
    reasonTitle: "추천 이유",
    reason: {
      deepDrop:
        "최근 고점보다 {drop}% 내려와 있어, 이미 가격이 많이 낮아진 상태입니다.",
      relativeDrop:
        "최근 고점보다 {drop}% 내려왔습니다. 큰 폭락이라고 단정할 정도는 아니지만, 현재 목록 안에서는 상대적으로 많이 내려온 편입니다.",
      freshPrice:
        "가격 정보가 최근 자료라서 지금 판단에 사용할 수 있습니다.",
      stalePrice:
        "가격 정보가 오래되어 실제 판단 전에는 다시 확인해야 합니다.",
      possibleOverreaction:
        "최근 회사 소식은 있지만, 이런 소식이 계속 나쁜 흐름으로 이어졌다는 표시가 강하지 않습니다.",
      unexplained:
        "하락을 설명할 뚜렷한 최근 회사 소식이 아직 보이지 않아, 원인 확인이 먼저 필요합니다.",
      persistentRisk:
        "최근 회사 소식이 과거에 투자자들이 조심했던 경우와 비슷해, 추천 순위를 낮췄습니다.",
      recentEvents:
        "최근 회사 소식 {count}건을 함께 확인했기 때문에, 단순히 가격만 보고 고른 종목은 아닙니다.",
      factorBad:
        "가장 큰 걱정거리: {label}. 비슷한 소식 뒤에는 투자자들이 조심스러워진 경우가 많았습니다.",
      factorGood:
        "도움이 되는 점: {label}. 비슷한 소식 뒤에는 시장이 더 좋게 받아들인 경우가 있었습니다.",
    },
  },
  common: { unknownError: "알 수 없는 오류" },
  search: {
    title: "종목 검색",
    subtitle:
      "티커·회사명·별칭으로 종목을 찾고, 이벤트에 없으면 회사명만으로 공시 분석을 실행하세요.",
    placeholder: "티커, 회사명, 또는 별칭…",
    searching: "검색 중…",
    noResults: "“{q}”에 해당하는 종목이 없습니다.",
    hint: "검색하려면 한 글자 이상 입력하세요.",
    eventsCount: "이벤트 {count}건",
    noEvents: "아직 이벤트 없음",
    tickerLabel: "티커 (선택)",
    nameLabel: "회사명",
    namePlaceholder: "선택",
    analyzeButton: "공시 분석",
    analyzing: "시작 중…",
    analyzeStarted:
      "{ticker} 분석을 시작했습니다. 추출이 끝나면 이벤트에 표시됩니다.",
    analyzeFailed: "분석 요청 실패",
    loginRequired: "분석 실행은 로그인이 필요합니다.",
    sessionExpired: "세션이 만료되었습니다. 다시 로그인한 뒤 분석을 실행하세요.",
    noListedCompany:
      "일치하는 KR/US 상장사를 찾지 못했습니다. SpaceX 같은 비상장사는 지원하지 않습니다.",
    providerUnavailable:
      "이 시장의 공시 제공자가 설정되어 있지 않습니다.",
  },
  screener: {
    title: "급락 종목",
    subtitle:
      "20일 고점 대비 큰폭 하락한 종목을, 검증된 사건 이력에 비추어 진단합니다.",
    disclaimer:
      "이것은 매수 추천이 아니라 진단입니다. 이 시스템은 검증된 상승 신호가 없습니다 — 검증된 사건유형은 전부 음(−)의 드리프트라 '오른다'를 주장하지 않습니다. '과잉반응 가능'은 백테스트 검증 전의 반등 후보 표시일 뿐입니다.",
    loading: "불러오는 중…",
    failTitle: "스크리너를 불러오지 못했습니다.",
    empty: "기준치 이상 하락한 신선한 가격의 종목이 없습니다.",
    thresholdLabel: "최소 낙폭",
    includeStale: "오래된 가격 포함",
    staleTag: "오래됨",
    col: {
      instrument: "종목",
      drawdown: "낙폭",
      priceRange: "현재가 / 20일 고점",
      diagnosis: "진단",
      recentEvents: "최근 사건",
      lean: "검증 성향",
      topFactor: "주요 요인",
    },
    diagnosis: {
      persistent_risk: "지속 악재",
      unexplained_drop: "원인 미상 하락",
      possible_overreaction: "과잉반응 가능",
      persistent_riskDesc:
        "최근 사건 + 검증된 음(−) 성향 — 하락이 이 종목의 이력과 일치하며, 주의가 이어질 가능성.",
      unexplained_dropDesc:
        "데이터상 이 하락을 설명하는 최근 사건이 없습니다. 신호가 아니라 관찰 — 사건 근거가 없습니다.",
      possible_overreactionDesc:
        "최근 사건은 있으나 검증된 음(−) 근거는 없음. 백테스트 검증 전의 반등 후보 — 매수 신호 아님.",
    },
    asOf: "{date} 기준",
    eventsInWindow: "30일 내 {count}건",
    noLean: "—",
    rebound: {
      title: "반등 백테스트",
      subtitle:
        "이런 하락 후 매수가 유효한가? 고정 규칙·표본외·비용 차감.",
      insufficient:
        "반등 엣지를 검증할 만큼 깨끗한 가격 이력이 아직 부족합니다 — 최근가를 리프레시해 쌓으세요. 그때까지 '과잉반응 가능'은 신호가 아니라 관찰로 유지됩니다.",
      marketAdjusted: "시장조정",
      raw: "원시(벤치마크 없음)",
      colHorizon: "기간",
      colSignals: "신호",
      colHitRate: "적중률",
      colNet: "평균 순수익",
      days: "{n}일",
      coverage: "채점 {scored} / 결과없음 {dropped}",
    },
  },
  watchlist: {
    title: "관심종목",
    subtitle: "알림을 받을 관심종목 목록",
    empty: "관심종목이 비어 있습니다.",
    howToAdd: "이벤트 목록이나 종목 페이지의 ☆ 버튼으로 관심종목을 추가하세요.",
    events: "이벤트",
  },
  alerts: {
    title: "알림",
    subtitle: "관심종목에서 주목할 만한 이벤트",
    empty: "아직 알림이 없습니다. 종목을 관심등록하면 주목할 이벤트를 알려드립니다.",
    markAllRead: "모두 읽음",
    groupCount: "알림 {count}개",
    conflictDesc: "모델 방향이 검증된 과거 드리프트와 충돌",
    significantDesc: "검증된 유의 사건유형",
    kindConflict: "충돌",
    kindSignificant: "유의",
  },
  watch: {
    watch: "관심등록",
    watching: "관심등록됨",
    loginToWatch: "로그인 후 관심등록",
    sessionExpired: "세션 만료 — 다시 로그인하세요",
  },
  auth: {
    login: "로그인",
    logout: "로그아웃",
    signInTitle: "로그인",
    signIn: "로그인",
    signingIn: "로그인 중…",
    cancel: "취소",
    username: "아이디",
    password: "비밀번호",
    invalidCreds: "아이디 또는 비밀번호가 올바르지 않습니다.",
    loginFailed: "로그인 실패",
  },
  ingest: {
    button: "데이터 수집",
    starting: "시작 중…",
    ingesting: "수집 중… (~1–2분)",
    started: "수집을 시작했습니다 — 곧 데이터가 표시됩니다",
    sessionExpired: "세션이 만료되었습니다 — 다시 로그인해 주세요.",
    errorPrefix: "오류: ",
    failed: "수집 실패",
    refresh: "새로고침",
    eventsLoaded: "✓ 이벤트 {n}건 로드됨",
    inProgress: "수집 진행 중 — 새로고침해 새 데이터를 확인하세요",
  },
  events: {
    loading: "이벤트 불러오는 중...",
    failTitle: "이벤트를 불러오지 못했습니다",
    backendHint: "백엔드가 {url} 에서 실행 중인지 확인하세요",
    title: "마켓 이벤트",
    count: "이벤트 {n}건",
    empty: "이벤트가 없습니다. 파이프라인을 실행해 공시를 수집하세요.",
    th: {
      ticker: "티커",
      instrument: "종목",
      eventType: "이벤트 유형",
      direction: "방향",
      confidence: "신뢰도",
      published: "공시일",
    },
    tab: {
      domestic: "국내 (KR)",
      overseas: "해외 (US)",
    },
    companyEvents: "이벤트 {n}건",
    noneInMarket: "이 시장의 이벤트가 없습니다.",
    expandHint: "기업을 선택하면 해당 기업의 이벤트를 최신순으로 보여줍니다.",
    searchLabel: "이벤트 검색",
    searchPlaceholder: "티커, 회사명, 이벤트 유형, 방향 검색...",
    searchHint: "검색은 선택한 시장과 신호 필터 안에서 적용됩니다.",
    searchCount: "일치하는 이벤트 {n}건",
    signalFilter: {
      all: "전체",
      conflict: "충돌만",
      needsReview: "미검토 충돌",
      validated: "검증된 것만",
    },
    reviewedMark: "검토됨",
    noneSearchResults: "이 검색어에 해당하는 이벤트가 없습니다.",
    noneMatchFilter: "이 필터에 해당하는 이벤트가 없습니다.",
    tip: {
      confidence:
        "신뢰도 — 모델이 이 이벤트의 방향·유형 판단을 얼마나 확신하는지입니다. 100%에 가까울수록 확신이 크다는 뜻이며, 실제 수익률을 보장하지는 않습니다.",
      signal:
        "신호 — 이 사건유형이 과거 실제로 시장을 어떻게 움직였는지(검증된 통계, n≥5·p<0.05)를 모델의 판단과 비교한 것입니다. 배지가 없으면 아직 이 유형의 검증된 신호가 없다는 뜻입니다.",
    },
  },
  stats: {
    loading: "통계 불러오는 중...",
    failTitle: "통계를 불러오지 못했습니다",
    title: "이벤트 유형별 반응 통계",
    buckets: "버킷 {n}개",
    subtitle:
      "이벤트 유형과 공시 후 기간(거래일)별로 묶은 시장조정 초과수익률의 평균과 분산.",
    empty: "아직 통계가 없습니다 — 먼저 이벤트를 수집하세요.",
    howToRead: "읽는 법",
    howToReadBody:
      "한 줄이 한 이벤트 유형입니다. 각 칸은 그 유형의 공시가 나온 뒤 N거래일 동안 주가가 시장 대비 평균 몇 % 움직였는지를 뜻합니다 — 초록은 상승, 빨강은 하락, n은 평균에 들어간 공시 건수입니다. 칸을 누르면 그 숫자의 근거가 된 실제 공시들이 펼쳐집니다.",
    th: {
      eventType: "이벤트 유형",
      horizon: "기간",
      samples: "표본 수",
      total: "표본",
      horizonGroup: "공시 후 기간(거래일)",
      mean: "평균 초과수익률",
      std: "표준편차",
    },
    noData: "데이터 없음",
    relatedHint:
      "칸을 선택하면 그 평균에 들어간 실제 공시들을 각각의 초과수익률과 함께 볼 수 있습니다.",
    relatedTitle: "{type} · D+{horizon} 의 근거 이벤트",
    relatedCount: "이벤트 {n}건",
    relatedSummary: "이 {n}건의 평균 = {mean}",
    relatedReturn: "초과수익률",
    relatedEmpty: "일치하는 이벤트가 없습니다.",
    signals: {
      title: "검증된 신호",
      subtitle:
        "평균 초과수익률이 표본도 충분하고(n≥5) 0과 통계적으로 구분되는(p<0.05) 사건유형만 — 데이터가 실제로 뒷받침하는 반응입니다. 나머지는 노이즈.",
      count: "유의 {n}개",
      empty:
        "아직 통계적으로 유의한 신호가 없습니다 — 표본이 결론을 낼 만큼 충분치 않습니다. 이벤트를 더 수집하세요.",
      negativeNote:
        "지금까지 검증된 신호는 전부 음(−)입니다: 해당 공시 뒤 시장 대비 하락 경향이라, 매수보다는 주의·회피 신호로 읽힙니다.",
      badge: "유의",
      th: {
        eventType: "사건유형",
        horizon: "기간",
        mean: "평균 초과수익",
        t: "t값",
        p: "p값",
        n: "n",
      },
    },
    backtest: {
      title: "워크포워드 백테스트",
      subtitle:
        "지평별 표본 외(out-of-sample) 신호 성과 — 거래비용 반영, look-ahead 차단.",
      modelLabel: "신호 모델",
      model: {
        event_type_history: "이벤트유형 히스토리",
        significant_event_type: "유의 유형만",
        macro_surprise: "거시 국면",
        price_momentum: "가격 모멘텀",
        combined: "결합",
        llm_direction: "LLM 방향",
      },
      loading: "백테스트 불러오는 중...",
      failTitle: "백테스트를 불러오지 못했습니다",
      empty: "아직 백테스트 결과가 없습니다 — 먼저 이벤트를 수집하세요.",
      th: {
        horizon: "기간",
        predictions: "예측수",
        hitRate: "적중률",
        gross: "총수익",
        net: "순수익",
        ic: "IC",
        coverage: "커버리지",
      },
      coverageHint: "사용 / 제외(결측)",
    },
    macro: {
      title: "거시 국면 분해",
      subtitle:
        "거시 국면 신호를 시리즈별로 따로 백테스트한 결과. 특정 경제 시리즈에 엣지가 몰리면 진짜 거시효과를, 모든 시리즈가 비슷하면 느린 캘린더/국면 프록시를 시사합니다.",
      loading: "거시 분해 불러오는 중...",
      failTitle: "거시 분해를 불러오지 못했습니다",
      empty: "surprise가 있는 거시 시리즈가 아직 없습니다.",
      th: {
        series: "거시 시리즈",
        icGroup: "지평별 정보계수(IC)",
        net: "순수익",
      },
      readHint:
        "각 칸은 해당 시리즈의 surprise 부호로 조건화했을 때의 표본외 정보계수(IC=예측과 실제의 상관)입니다. 마우스를 올리면 거래비용 반영 순수익·표본수가 보입니다. 초록 = 양(+)의 예측상관.",
    },
    calibration: {
      title: "신뢰도 캘리브레이션",
      subtitle:
        "신뢰도 0.7 예측이 실제로 ~70% 맞을까? 방향 예측을 신뢰도 구간별로 묶어, 지평별로 실제 적중률과 모델이 말한 신뢰도를 비교합니다.",
      horizonLabel: "지평",
      loading: "캘리브레이션 불러오는 중...",
      failTitle: "캘리브레이션을 불러오지 못했습니다",
      empty: "캘리브레이션할 방향 예측이 아직 충분하지 않습니다.",
      summary:
        "방향 예측 {n}건 · 평균 신뢰도 {conf} vs 실제 적중률 {hit}",
      ece: "캘리브레이션 오차(ECE)",
      brier: "Brier 점수",
      verdict: {
        over: "과신 — 말한 신뢰도가 실제 정확도보다 높습니다.",
        under: "과소신뢰 — 실제 정확도가 말한 신뢰도보다 높습니다.",
        good: "잘 보정됨 — 말한 신뢰도가 실제 정확도를 잘 따라갑니다.",
      },
      th: {
        band: "신뢰도 구간",
        n: "n",
        meanConf: "평균 신뢰도",
        hitRate: "실제 적중률",
        gap: "격차",
      },
      readHint:
        "격차 = 평균 신뢰도 − 실제 적중률. 양수(주황) = 그 구간에서 과신, 음수(초록) = 과소신뢰. 중립(neutral) 예측과 실현수익이 없는 이벤트는 제외됩니다. ECE는 표본가중 평균 격차, Brier는 신뢰도와 결과의 평균제곱오차(낮을수록 좋음)입니다.",
    },
  },
  eventDetail: {
    loading: "이벤트 불러오는 중...",
    failTitle: "이벤트를 불러오지 못했습니다",
    unknownInstrument: "알 수 없는 종목",
    model: "모델",
    version: "버전",
    sourceDoc: "원본 문서",
    evidence: "근거",
    industries: "산업",
    channels: "채널",
    signal: {
      title: "검증신호",
      subtitle:
        "이 사건유형이 과거 실제로 시장을 어떻게 움직였는지 — 그리고 모델 판단과 일치하는지.",
      verdictLabel: "모델 vs 실측",
      conflict:
        "충돌 — 모델은 {llm}으로 봤지만, 이 사건유형의 검증된 실측은 {hist} 신호입니다.",
      agree: "일치 — 모델의 {llm} 판단이 검증된 실측({hist})과 부합합니다.",
      info: "모델은 중립으로 봤고, 이 사건유형의 검증된 실측은 {hist} 신호입니다.",
      none:
        "이 사건유형은 아직 통계적으로 유의한 검증신호가 없습니다(n≥5, p<0.05). 모델 판단은 미검증으로 보세요.",
      up: "상승",
      down: "하락",
      short: {
        conflict: "충돌",
        conflictTitle: "모델 판단이 검증된 실측과 충돌",
        agree: "검증됨",
        agreeTitle: "모델 판단이 검증된 실측과 일치",
        info: "신호",
        infoTitle: "검증신호 있음, 모델은 중립",
      },
      badge: {
        conflict:
          "충돌 — 모델이 읽은 방향이 이 사건유형의 검증된 과거 실측(통계적으로 유의한 방향, n≥5·p<0.05)과 반대입니다. 한 번 더 확인해 볼 필요가 있습니다.",
        agree:
          "검증됨 — 모델이 읽은 방향이 이 사건유형의 검증된 과거 드리프트와 일치합니다.",
        info:
          "신호 — 이 사건유형은 통계적으로 유의한(n≥5·p<0.05) 과거 방향성이 있지만, 모델은 중립으로 봤습니다. 과거 실측 방향을 참고하세요.",
      },
    },
    review: {
      title: "검토·수정",
      subtitle:
        "모델 판단을 교정합니다. 방향·유형은 통계에 즉시 반영되고, 회사 변경은 해당 종목 수익률을 다시 계산합니다.",
      direction: "방향",
      eventType: "사건유형",
      company: "회사",
      confidence: "신뢰도",
      recomputeNote:
        "회사를 바꾸면 가격을 다시 가져와 이 이벤트의 수익률을 재계산합니다.",
      save: "저장",
      saving: "저장 중…",
      noChanges: "변경 없음",
      failed: "저장 실패. 다시 시도하세요.",
      recomputeFailed:
        "회사 교정 중 가격 재계산에 실패했습니다. 변경 사항은 저장되지 않았습니다.",
      sessionExpired: "세션 만료 — 다시 로그인하세요.",
      reviewedAt: "{date} 사람이 검토함",
    },
  },
  instrument: {
    loading: "종목 타임라인 불러오는 중...",
    failTitle: "종목을 불러오지 못했습니다",
    timeline: "이벤트 타임라인",
    eventsCount: "(이벤트 {n}건)",
    empty: "이 종목에 기록된 이벤트가 없습니다.",
    conf: "신뢰도",
    signal: {
      title: "종목 판정",
      subtitle:
        "이 종목의 사건 유형들이 과거 실제로 어떤 결과로 이어졌는지(검증된 사건유형 드리프트)를 집계. 가격 예측이 아닙니다.",
      basis: "검증 사건 {n}건 기준",
      none: "이 종목은 아직 검증신호를 낸 사건이 없습니다.",
      netDrift: "평균 검증 드리프트",
      validatedEvents: "검증 사건 수",
      conflicts: "충돌(미검토)",
      lean: {
        bearish: "주의 — 검증된 실측이 하락 우위입니다.",
        bullish: "우호 — 검증된 실측이 상승 우위입니다.",
        neutral: "혼조 — 뚜렷한 검증 방향 없음.",
        none: "검증신호 부족.",
      },
    },
    factors: {
      title: "상승 · 하락 요인",
      subtitle:
        "이 종목 이력의 사건 유형 중 검증된 드리프트를 가진 것 — 무엇이 어느 방향으로 움직일 수 있는지.",
      upside: "상승 요인",
      downside: "하락 요인",
      none: "확인된 요인 없음.",
      detail: "D+{horizon} · {count}건 · 최근 {date}",
    },
  },
  rankings: {
    title: "종목 랭킹",
    subtitle:
      "모든 종목을 확신도·최근성 가중 검증 드리프트로 랭킹 — 종목 간 매수판단 뷰. 최근·고확신 사건이 낡거나 저확신 사건보다 크게 반영됩니다. 가격 예측이 아니며, 과거 실측상 가장 주의할 종목이 위로.",
    loading: "랭킹 불러오는 중...",
    failTitle: "랭킹을 불러오지 못했습니다",
    empty:
      "아직 랭킹에 필요한 검증 사건이 충분한 종목이 없습니다. 이벤트를 더 적재해 검정력을 확보하세요.",
    weightingNote:
      "가중: 각 검증 사건 × LLM 확신도 × 최근성(반감기 {halfLife}일).",
    col: {
      rank: "#",
      instrument: "종목",
      lean: "판정",
      score: "가중 드리프트",
      simpleMean: "단순 평균",
      validated: "검증",
      conflicts: "충돌",
      topFactor: "주요 요인",
    },
    lean: { bearish: "주의", bullish: "우호", neutral: "혼조" },
    factor: "{label} {drift} ({count}건)",
    conflictsCell: "{total} (미검토 {unreviewed})",
    tip: {
      lean:
        "판정 — 검증된 과거 실측을 종합한 이 종목의 방향 성향입니다. 주의(하락 우위)·우호(상승 우위)·혼조(뚜렷한 방향 없음).",
      score:
        "가중 드리프트 — 이 종목의 검증된 사건들의 사건후 평균 수익률(드리프트)을, 각 사건의 모델 확신도와 최근성(최근일수록 크게)으로 가중해 합산한 값입니다. 랭킹은 이 값으로 정렬됩니다.",
      simpleMean:
        "단순 평균 — 같은 검증 사건들의 드리프트를 가중 없이 단순 평균한 값입니다. 가중 드리프트와 비교하면 확신도·최근성 보정이 얼마나 영향을 줬는지 알 수 있습니다.",
      validated:
        "검증 — 통계적으로 유의한(n≥5·p<0.05) 검증 신호를 가진 이 종목의 사건 수입니다.",
      conflicts:
        "충돌 — 모델이 읽은 방향이 검증된 과거 실측과 반대인 사건 수입니다. 괄호 안은 그중 아직 사람이 검토하지 않은 건수입니다.",
      topFactor:
        "주요 요인 — 가중 드리프트에 가장 크게 기여한 사건유형과 그 사건후 평균 수익률입니다.",
    },
  },
  direction: { positive: "긍정", negative: "부정", neutral: "중립" },
  chart: {
    title: "초과수익률 (%)",
    noData: "수익률 데이터가 없습니다",
    noDataWhy:
      "수익률은 공시 시점 이후 정해진 거래일(예: 1·5·20·60거래일)이 지나야 계산됩니다. 이벤트가 너무 최근이라 그 기간이 아직 지나지 않았거나, 해당 종목의 가격 데이터가 아직 수집되지 않은 경우 그래프가 비어 있습니다.",
    titleTip:
      "초과수익률 — 종목의 실제 수익률에서 같은 기간 시장(지수) 수익률을 뺀 값입니다. 시장 전체 흐름을 제거해, 이 이벤트가 종목에 준 영향만 따로 볼 수 있게 한 지표입니다.",
    abnormalReturn: "초과수익률",
    rawReturn: "원수익률",
    sectorAdjusted: "섹터조정",
    marketReturn: "시장수익률",
    abnormal: "초과",
    raw: "원",
    market: "시장",
  },
  scores: {
    title: "점수 구성",
    confidence: "신뢰도",
    surprise: "서프라이즈",
    novelty: "신규성",
    sourceReliability: "출처 신뢰도",
    titleTip:
      "각 점수는 0~100%로 표시됩니다.\n• 신뢰도: 모델이 이 이벤트 판단을 얼마나 확신하는지.\n• 서프라이즈: 소식이 시장 예상과 얼마나 달랐는지 — 높을수록 예상 밖입니다.\n• 신규성: 정보가 얼마나 새로운지 — 반복·정례 공시일수록 낮습니다.\n• 출처 신뢰도: 공시·자료 출처가 얼마나 믿을 만한지.",
  },
  macro: {
    title: "거시 서프라이즈",
    count: "{n}개 시리즈",
    loading: "거시 지표 불러오는 중...",
    failTitle: "거시 지표를 불러오지 못했습니다",
    subtitle:
      "경제지표(물가·고용·금리 등)가 시장의 사전 예상과 얼마나 다르게 나왔는지를 모아 봅니다. 모든 종목과 이벤트가 거래되는 배경, 즉 시장 전체 분위기를 좌우하는 것은 '발표값 자체'가 아니라 '예상과의 차이(서프라이즈)'입니다. 이 서프라이즈를 하나의 표준화된 화면에 모아, 급락·이벤트를 해석할 때 배경 국면으로 활용하기 위한 탭입니다.",
    empty: "아직 거시 데이터가 없습니다 — 먼저 거시 수집을 실행하세요.",
    th: {
      series: "시리즈",
      reference: "기준일",
      released: "발표값",
      expected: "예상값",
      surprise: "서프라이즈 (σ)",
    },
    tip: {
      released: "발표값 — 이 지표에 대해 실제로 발표된 수치입니다.",
      expected:
        "예상값 — 발표 전 시장이 기대한 값입니다. 컨센서스(전문가 예측 합의)가 있으면 그것을, 없으면 과거 추세 기준선 예측을 씁니다.",
      surprise:
        "서프라이즈(σ) — (발표값 − 예상값)을 그 지표의 과거 변동성(표준편차)으로 나눈 값입니다. +면 예상보다 좋게/높게, −면 예상보다 나쁘게/낮게 나왔다는 뜻이고, 숫자가 클수록 예상 밖 정도가 큽니다. 단위 σ(시그마)는 '평소 오차의 몇 배냐'를 뜻해, 서로 다른 지표를 같은 잣대로 비교할 수 있게 합니다.",
    },
    baseline: "기준선",
    consensus: "컨센서스",
  },
  ledger: {
    title: "가계부",
    subtitle: "카드 명세서 PDF를 업로드해 지출 내역으로 정리합니다.",
    loginRequired: "가계부를 보려면 로그인하세요.",
    fileLabel: "명세서 PDF",
    fileHelp: "PDF 명세서를 선택하세요",
    missingFile: "먼저 명세서 PDF를 선택하세요.",
    passwordLabel: "명세서 비밀번호",
    passwordPlaceholder: "PDF 비밀번호 입력",
    passwordRequired: "명세서 비밀번호를 입력하세요.",
    invalidPassword: "명세서 비밀번호가 올바르지 않습니다.",
    load: "업로드 후 파싱",
    loading: "가계부 불러오는 중...",
    parsing: "명세서 업로드 및 파싱 중...",
    failTitle: "가계부를 불러오지 못했습니다",
    sessionExpired: "세션이 만료되었습니다. 다시 로그인한 뒤 명세서를 업로드해 주세요.",
    monthLabel: "명세월",
    savedMonths: "저장된 월 {n}개",
    listLoading: "저장된 월 불러오는 중...",
    detailLoading: "선택한 명세서 불러오는 중...",
    noSavedStatements: "저장된 명세서가 없습니다.",
    file: "파일",
    uploadedAt: "업로드일",
    statementMonth: "명세월",
    period: "이용기간",
    paymentDue: "결제일",
    billedTotal: "청구금액",
    foreignTotal: "해외 청구",
    parsedTotal: "파싱 거래합계",
    entries: "거래 {n}건",
    warnings: "확인 필요",
    categories: "카테고리 합계",
    th: {
      date: "일자",
      category: "분류",
      description: "사용처",
      card: "카드",
      amount: "금액",
    },
    empty: "파싱된 거래 내역이 없습니다.",
    chartTitle: "카드값 순위",
    chartSubtitle: "금액 기준 상위 10개 카테고리",
    windowMonth: "이번 달",
    windowYear: "최근 1년",
    chartLoading: "카테고리 합계 불러오는 중...",
    chartEmpty: "그래프로 표시할 카테고리 합계가 없습니다.",
    chartAmount: "금액",
    topTitle: "최다 지출 내역",
    topSubtitle: "금액 기준 상위 10건 (날짜 + 사용처)",
    topEmpty: "순위로 표시할 거래가 없습니다.",
  },
  passbook: {
    title: "통장관리",
    subtitle: "은행 거래내역 PDF를 업로드해 입출금 내역으로 정리합니다.",
    loginRequired: "통장 내역을 보려면 로그인하세요.",
    fileLabel: "거래내역 PDF",
    fileHelp: "PDF 거래내역을 선택하세요",
    missingFile: "먼저 거래내역 PDF를 선택하세요.",
    passwordLabel: "PDF 비밀번호",
    passwordPlaceholder: "PDF 비밀번호 입력",
    passwordRequired: "PDF 비밀번호를 입력하세요.",
    invalidPassword: "PDF 비밀번호가 올바르지 않습니다.",
    load: "업로드 후 파싱",
    parsing: "거래내역 업로드 및 파싱 중...",
    failTitle: "통장 내역을 불러오지 못했습니다",
    sessionExpired: "세션이 만료되었습니다. 다시 로그인한 뒤 거래내역을 업로드해 주세요.",
    monthLabel: "거래월",
    savedMonths: "저장된 월 {n}개",
    listLoading: "저장된 월 불러오는 중...",
    detailLoading: "선택한 거래내역 불러오는 중...",
    noSavedStatements: "저장된 거래내역이 없습니다.",
    file: "파일",
    uploadedAt: "업로드일",
    statementMonth: "거래월",
    account: "계좌번호",
    holder: "예금주",
    period: "조회기간",
    closingBalance: "총잔액",
    withdrawalTotal: "출금 합계",
    depositTotal: "입금 합계",
    entries: "거래 {n}건",
    warnings: "확인 필요",
    th: {
      date: "일자",
      time: "시간",
      summary: "적요",
      description: "내용",
      withdrawal: "출금",
      deposit: "입금",
      balance: "잔액",
      branch: "거래점",
    },
    empty: "파싱된 거래 내역이 없습니다.",
    chartTitle: "카테고리 순위",
    chartSubtitle: "금액 기준 상위 10개 카테고리",
    windowMonth: "이번 달",
    windowYear: "최근 1년",
    directionOut: "출금",
    directionIn: "입금",
    chartLoading: "카테고리 합계 불러오는 중...",
    chartEmpty: "그래프로 표시할 카테고리 합계가 없습니다.",
    chartAmount: "금액",
    topTitleOut: "최다 출금 내역",
    topTitleIn: "최다 입금 내역",
    topSubtitle: "금액 기준 상위 10건 (날짜 + 내용)",
    topEmpty: "순위로 표시할 거래가 없습니다.",
  },
  customize: {
    th: { category: "카테고리" },
    edit: "수정",
    edited: "수정됨",
    reassignTitle: "카테고리 변경",
    categoryLabel: "카테고리",
    newCategoryOption: "+ 새 카테고리…",
    newCategoryPlaceholder: "새 카테고리 이름",
    scopeSingle: "이 항목만",
    scopeRule: "같은 항목 전체 (규칙 저장)",
    keywordLabel: "키워드",
    ruleHint: "가맹점·적요에 이 키워드가 포함된 모든 거래가 지금과 앞으로의 명세서에서 재분류됩니다.",
    categoryRequired: "카테고리 이름을 입력하세요.",
    keywordRequired: "키워드를 입력하세요.",
    revert: "자동 분류로 되돌리기",
    cancel: "취소",
    apply: "적용",
    managerTitle: "카테고리 관리",
    managerSummary: "커스텀 {categories}개 · 규칙 {rules}개",
    customCategories: "커스텀 카테고리",
    add: "추가",
    deleteCategory: "{name} 카테고리 삭제",
    noCustomCategories: "아직 커스텀 카테고리가 없습니다.",
    rulesTitle: "키워드 규칙",
    delete: "삭제",
    noRules: "아직 저장된 규칙이 없습니다.",
  },
};

const dicts: Record<Lang, Dict> = { en, ko };
const locales: Record<Lang, string> = { en: "en-US", ko: "ko-KR" };

function lookup(dict: Dict, key: string): string {
  const value = key.split(".").reduce<string | Dict | undefined>(
    (acc, part) => (acc && typeof acc === "object" ? acc[part] : undefined),
    dict
  );
  return typeof value === "string" ? value : key;
}

interface I18nContextValue {
  lang: Lang;
  locale: string;
  setLang: (lang: Lang) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  // Default to English to match the server-rendered markup; the stored choice
  // is applied after mount (same pattern as AuthProvider) to avoid hydration
  // mismatches.
  const [lang, setLangState] = useState<Lang>("en");

  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = localStorage.getItem(LANG_KEY);
    if (stored === "en" || stored === "ko") setLangState(stored);
  }, []);

  useEffect(() => {
    if (typeof document !== "undefined") document.documentElement.lang = lang;
  }, [lang]);

  function setLang(next: Lang): void {
    setLangState(next);
    if (typeof window !== "undefined") localStorage.setItem(LANG_KEY, next);
  }

  function t(key: string, vars?: Record<string, string | number>): string {
    let str = lookup(dicts[lang], key);
    if (vars) {
      for (const [name, value] of Object.entries(vars)) {
        str = str.replace(`{${name}}`, String(value));
      }
    }
    return str;
  }

  return (
    <I18nContext.Provider value={{ lang, locale: locales[lang], setLang, t }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within <I18nProvider>");
  return ctx;
}

/** Segmented EN | 한국어 control used in the site header. */
export function LanguageToggle() {
  const { lang, setLang } = useI18n();
  const options: { value: Lang; label: string }[] = [
    { value: "en", label: "EN" },
    { value: "ko", label: "한국어" },
  ];
  return (
    <div
      role="group"
      aria-label="Language"
      className="inline-flex rounded-md border border-gray-200 bg-gray-50 p-0.5 text-xs font-medium"
    >
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => setLang(opt.value)}
          aria-pressed={lang === opt.value}
          className={`rounded px-2.5 py-1 transition-colors ${
            lang === opt.value
              ? "bg-white text-indigo-600 shadow-sm"
              : "text-gray-500 hover:text-gray-700"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
