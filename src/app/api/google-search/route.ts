import { NextRequest, NextResponse } from 'next/server';
import crypto from 'crypto';

import { supabaseAdmin } from '@/lib/supabase-admin';
import { extractSignal, RawPost } from '@/lib/ai-extractor';

// ===============================
// Default Search Keywords
// ===============================

// ===============================
// Default Search Keywords — Forum-Targeted + Multi-Brand
// ===============================

// Forum site: search — high-quality demand signals from real users
const FORUM_KEYWORDS = [
  // TractorByNet — largest tractor community (North America)
  'site:tractorbynet.com Kubota parts need OR broken OR help',
  'site:tractorbynet.com Kubota seat replacement',
  'site:tractorbynet.com Kubota hydraulic pump leaking OR failure',
  'site:tractorbynet.com John Deere parts need OR broken',

  // AgTalk — professional ag machinery forum
  'site:agtalk.net Kubota broken OR fix OR parts',
  'site:agtalk.net tractor parts where to buy',

  // Yesterday's Tractors — repair & parts advice
  'site:yesterdaystractors.com Kubota parts OR repair',
  'site:yesterdaystractors.com tractor seat OR pump OR filter',

  // Reddit — younger users, buying advice
  'site:reddit.com Kubota tractor parts help',
  'site:reddit.com/r/tractors tractor parts broken',

  // The Farming Forum — UK/Europe market
  'site:thefarmingforum.co.uk tractor parts needed',
];

// General web search — broader funnel coverage
const GENERAL_KEYWORDS = [
  // Middle funnel: solution-seeking (high conversion)
  '"Kubota" wear problems forum',
  '"John Deere" parts where to buy Africa',
  '"Yanmar" harvester parts broken fix',
  'best tractor filter to stock before harvest season',

  // Top funnel: known buyers
  '"Kubota" replacement parts shipping OR delivery',
  '"tractor spare parts" forum Southeast Asia OR Africa',

  // Bottom funnel: specific model + installation
  '"Kubota L3400" hydraulic pump installation guide',
  '"Kubota M9540" belt replacement chart',
];

const DEFAULT_KEYWORDS = [...FORUM_KEYWORDS, ...GENERAL_KEYWORDS];

// ===============================
// Types
// ===============================

interface SerpResult {
  title: string;
  link: string;
  snippet: string;
  displayed_link?: string;
}

interface SerpApiResponse {
  organic_results?: SerpResult[];
  search_metadata?: {
    status: string;
    total_time_taken: number;
  };
  error?: string;
}

// ===============================
// Generate Stable ID
// ===============================

function generateHash(text: string) {
  return crypto.createHash('sha256').update(text).digest('hex');
}

// ===============================
// SerpAPI Search
// ===============================

async function performSerpSearch(
  query: string,
  num: number = 10
): Promise<SerpResult[]> {
  const apiKey = process.env.SERPAPI_KEY;

  if (!apiKey) {
    throw new Error("Missing SERPAPI_KEY in environment variables");
  }

  const url = new URL("https://serpapi.com/search");
  url.searchParams.set("api_key", apiKey);
  url.searchParams.set("q", query);
  url.searchParams.set("num", String(num));
  url.searchParams.set("gl", "us");   // global search
  url.searchParams.set("hl", "en");   // English results

  const response = await fetch(url.toString());

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`SerpAPI Error ${response.status}: ${error}`);
  }

  const data: SerpApiResponse = await response.json();

  if (data.error) {
    throw new Error(`SerpAPI Error: ${data.error}`);
  }

  return data.organic_results || [];
}

// ===============================
// Process Search Results
// ===============================

async function processSearchResults(items: SerpResult[]): Promise<number> {
  let extractedCount = 0;

  for (const item of items) {
    try {
      const postId = `serp-${generateHash(item.link)}`;

      const post: RawPost = {
        id: postId,
        content: `${item.title}. ${item.snippet}`,
        author: item.displayed_link || item.link,
        location: undefined,
        timestamp: new Date().toISOString(),
        source: "serpapi_search",
        url: item.link
      };

      const signal = extractSignal(post);

      if (!signal) {
        continue;
      }

      // prevent duplicate
      const { data: existing } = await supabaseAdmin
        .from("signals")
        .select("id")
        .eq("source_url", item.link)
        .maybeSingle();

      if (existing) {
        continue;
      }

      const { error } = await supabaseAdmin
        .from("signals")
        .insert({
          ...signal,
          source_url: item.link,
          processed_at: new Date().toISOString(),
          source: "serpapi_search"
        });

      if (error) {
        console.error("INSERT ERROR:", error.code, error.message);
      } else {
        extractedCount++;
      }
    } catch (error) {
      console.error("Process result failed:", error);
    }
  }

  return extractedCount;
}

// ===============================
// POST
// ===============================

export async function POST(request: NextRequest) {
  try {
    const body = await request.json().catch(() => ({}));
    let { keywords } = body;

    let searchKeywords = Array.isArray(keywords) && keywords.length
      ? keywords
      : DEFAULT_KEYWORDS;

    // limit api cost — rotate through keywords, 15 per run
    searchKeywords = searchKeywords.slice(0, 15);

    console.log(`Searching ${searchKeywords.length} keywords via SerpAPI`);

    let totalResults = 0;
    let totalSignals = 0;
    const errors: string[] = [];

    for (const keyword of searchKeywords) {
      try {
        console.log("Searching:", keyword);

        const results = await performSerpSearch(keyword, 10);
        console.log(`  → ${results.length} results`);

        if (results.length > 0) {
          const count = await processSearchResults(results);
          totalResults += results.length;
          totalSignals += count;
          console.log(`  → ${count} signals extracted`);
        }

        // avoid rate limit (SerpAPI: ~3 req/s free tier)
        await new Promise(r => setTimeout(r, 1500));
      } catch (error) {
        const msg = `Keyword "${keyword}" failed: ${error}`;
        errors.push(msg);
        console.error(msg);
      }
    }

    return NextResponse.json({
      success: true,
      keywords_searched: searchKeywords.length,
      total_results: totalResults,
      signals_extracted: totalSignals,
      source: "serpapi",
      errors: errors.length ? errors : undefined
    });

  } catch (error) {
    console.error("Search API failed:", error);
    return NextResponse.json(
      {
        success: false,
        error: String(error),
        hint: "Check SERPAPI_KEY in .env.local"
      },
      { status: 500 }
    );
  }
}

// ===============================
// GET
// ===============================

export async function GET() {
  return NextResponse.json({
    service: "SerpAPI Search Signal Extractor",
    endpoint: "POST /api/google-search",
    defaultKeywords: DEFAULT_KEYWORDS,
    requiredEnv: ["SERPAPI_KEY"],
    configured: Boolean(process.env.SERPAPI_KEY)
  });
}
