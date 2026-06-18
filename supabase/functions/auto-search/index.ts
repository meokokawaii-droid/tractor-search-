import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Client-Info, Apikey",
};

const DEFAULT_KEYWORDS = [
  'Kubota tractor part repair',
  'Kubota seat replacement',
  'Kubota filter needed site:tractorbynet.com',
  'Kubota hydraulic pump problem',
  'Kubota L series parts wanted',
  'agricultural machinery spare parts Africa',
  'tractor part supplier Southeast Asia',
];

interface SearchResult {
  title: string;
  link: string;
  snippet: string;
  displayLink: string;
}

async function performGoogleSearch(query: string): Promise<SearchResult[]> {
  const apiKey = Deno.env.get('SERPAPI_KEY');

  if (!apiKey) {
    throw new Error('SerpApi key not configured');
  }

  const url = new URL('https://serpapi.com/search');
  url.searchParams.set('q', query);
  url.searchParams.set('api_key', apiKey);
  url.searchParams.set('num', '10');
  url.searchParams.set('engine', 'google');

  const response = await fetch(url.toString());
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`SerpApi error: ${response.status} - ${errorText}`);
  }

  const data = await response.json();
  const organicResults = data.organic_results || [];

  return organicResults.map((item: any) => ({
    title: item.title || '',
    link: item.link || '',
    snippet: item.snippet || '',
    displayLink: item.displayed_link || '',
  }));
}

function extractSignal(content: string): {
  region: string | null;
  vehicle_model: string | null;
  part_category: string | null;
  urgency: 'high_demand' | 'inquiry';
} | null {
  const lowerContent = content.toLowerCase();

  if (!lowerContent.includes('kubota') && !lowerContent.includes('久保田')) {
    return null;
  }

  const partsKeywords = [
    'filter', 'seat', 'pump', 'engine', 'transmission', 'hydraulic',
    'belt', 'bearing', 'gasket', 'valve', 'cylinder', 'tire', 'battery',
    'radiator', 'clutch', 'brake', 'steering', 'parts', 'repair', 'replacement',
    '配件', '滤芯', '座椅', '泵'
  ];

  const hasParts = partsKeywords.some(kw => lowerContent.includes(kw));
  if (!hasParts) return null;

  const regionKeywords: Record<string, string[]> = {
    'Africa': ['africa', 'nigeria', 'kenya', 'ghana', 'tanzania'],
    'Southeast Asia': ['thailand', 'vietnam', 'indonesia', 'malaysia', 'philippines'],
    'South Asia': ['india', 'pakistan', 'bangladesh'],
    'Middle East': ['dubai', 'saudi', 'iran', 'uae'],
    'Latin America': ['brazil', 'mexico', 'argentina'],
    'Europe': ['germany', 'france', 'uk', 'europe'],
    'North America': ['usa', 'canada', 'america'],
  };

  let region: string | null = null;
  for (const [r, keywords] of Object.entries(regionKeywords)) {
    if (keywords.some(kw => lowerContent.includes(kw))) {
      region = r;
      break;
    }
  }

  const modelMatch = content.match(/[LM]\s*\d{3,4}/i);
  const vehicle_model = modelMatch ? modelMatch[0] : null;

  const categoryMap: Record<string, string> = {
    'filter': 'Filter', '滤芯': 'Filter',
    'seat': 'Seat', '座椅': 'Seat',
    'pump': 'Pump', '泵': 'Pump',
    'engine': 'Engine', '发动机': 'Engine',
    'transmission': 'Transmission', '变速箱': 'Transmission',
    'hydraulic': 'Hydraulic System', '液压': 'Hydraulic System',
    'battery': 'Battery', '电瓶': 'Battery',
    'tire': 'Tire', '轮胎': 'Tire',
  };

  let part_category: string | null = null;
  for (const [kw, cat] of Object.entries(categoryMap)) {
    if (lowerContent.includes(kw)) {
      part_category = cat;
      break;
    }
  }

  const urgentWords = ['urgent', 'need', 'looking for', 'broken', 'problem', '急需', '求购'];
  const urgency: 'high_demand' | 'inquiry' = urgentWords.some(w => lowerContent.includes(w))
    ? 'high_demand'
    : 'inquiry';

  return { region, vehicle_model, part_category, urgency };
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 200, headers: corsHeaders });
  }

  try {
    const supabaseUrl = Deno.env.get('SUPABASE_URL')!;
    const supabaseKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
    const authHeader = req.headers.get('Authorization');

    const cronSecret = Deno.env.get('CRON_SECRET');
    if (cronSecret && authHeader !== `Bearer ${cronSecret}`) {
      return new Response(
        JSON.stringify({ error: 'Unauthorized' }),
        { status: 401, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    let keywords = DEFAULT_KEYWORDS;
    if (req.method === 'POST') {
      const body = await req.json().catch(() => ({}));
      if (body.keywords?.length > 0) {
        keywords = body.keywords;
      }
    }

    const results: Array<{
      keyword: string;
      found: number;
      extracted: number;
      error?: string;
      debug?: string[];
    }> = [];

    let totalExtracted = 0;

    for (const keyword of keywords) {
      const debugLogs: string[] = [];
      try {
        const items = await performGoogleSearch(keyword);

        let extracted = 0;
        for (const item of items) {
          const content = `${item.title} ${item.snippet}`;
          const signal = extractSignal(content);

          if (!signal) {
            debugLogs.push(`SKIPPED (no signal match): ${content.slice(0, 60)}`);
            continue;
          }

          // Check for duplicates
          const checkUrl = `${supabaseUrl}/rest/v1/signals?source_url=eq.${encodeURIComponent(item.link)}&select=id`;
          const checkRes = await fetch(checkUrl, {
            headers: {
              'apikey': supabaseKey,
              'Authorization': `Bearer ${supabaseKey}`,
            }
          });

          if (!checkRes.ok) {
            const errText = await checkRes.text();
            debugLogs.push(`DUPLICATE CHECK FAILED (${checkRes.status}): ${errText.slice(0, 200)}`);
            continue;
          }

          const existing = await checkRes.json();

          if (existing.length > 0) {
            debugLogs.push(`SKIPPED (already exists): ${item.link.slice(0, 60)}`);
            continue;
          }

          // Insert new signal
          const insertRes = await fetch(`${supabaseUrl}/rest/v1/signals`, {
            method: 'POST',
            headers: {
              'apikey': supabaseKey,
              'Authorization': `Bearer ${supabaseKey}`,
              'Content-Type': 'application/json',
              'Prefer': 'return=minimal'
            },
            body: JSON.stringify({
              raw_content: content,
              region: signal.region,
              vehicle_model: signal.vehicle_model,
              part_category: signal.part_category,
              urgency: signal.urgency,
              source: 'serpapi_google_search',
              source_url: item.link,
              processed_at: new Date().toISOString()
            })
          });

          if (!insertRes.ok) {
            const errText = await insertRes.text();
            debugLogs.push(`INSERT FAILED (${insertRes.status}): ${errText.slice(0, 200)}`);
            continue;
          }

          debugLogs.push(`INSERTED OK: ${item.link.slice(0, 60)}`);
          extracted++;
          totalExtracted++;
        }

        results.push({
          keyword,
          found: items.length,
          extracted,
          debug: debugLogs
        });

        await new Promise(r => setTimeout(r, 1000));

      } catch (e) {
        results.push({
          keyword,
          found: 0,
          extracted: 0,
          error: String(e),
          debug: debugLogs
        });
      }
    }

    return new Response(
      JSON.stringify({
        success: true,
        total_extracted: totalExtracted,
        keywords_processed: keywords.length,
        results
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );

  } catch (error) {
    return new Response(
      JSON.stringify({ error: String(error) }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});