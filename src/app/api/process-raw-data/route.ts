import { NextRequest, NextResponse } from 'next/server';
import { supabaseAdmin } from '@/lib/supabase-admin';
import { extractSignal, checkForUrgentAlert, RawPost, ExtractedSignal } from '@/lib/ai-extractor';

// Handle various data formats from different sources
function parseIncomingData(body: any): RawPost[] {
  const posts: RawPost[] = [];

  // Format 1: Direct array of posts
  if (Array.isArray(body)) {
    return body.map((item, index) => ({
      id: item.id || `post-${index}`,
      content: item.text || item.content || item.message || item.body || item.snippet || '',
      author: item.author || item.username || item.user?.name || null,
      location: item.location || item.user?.location || null,
      timestamp: item.timestamp || item.createdAt || item.created_at || item.published || null,
      source: item.source || item.platform || 'web',
      url: item.url || item.link || null,
    }));
  }

  // Format 2: Google Search results
  if (body.items && Array.isArray(body.items)) {
    return body.items.map((item: any, index: number) => ({
      id: item.id || `google-${index}`,
      content: item.snippet || item.title || '',
      author: item.displayLink || null,
      location: null,
      timestamp: null,
      source: 'google_search',
      url: item.link || null,
    }));
  }

  // Format 3: Wrapped data (data, items, posts)
  if (body.data && Array.isArray(body.data)) {
    return parseIncomingData(body.data);
  }
  if (body.posts && Array.isArray(body.posts)) {
    return parseIncomingData(body.posts);
  }

  // Format 4: Single post object
  if (body.content || body.text || body.message || body.body || body.snippet) {
    return [{
      id: body.id || 'single-post',
      content: body.text || body.content || body.message || body.body || body.snippet || '',
      author: body.author || body.username || null,
      location: body.location || null,
      timestamp: body.timestamp || body.createdAt || null,
      source: body.source || 'web',
      url: body.url || body.link || null,
    }];
  }

  return [];
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    console.log('Received data:', JSON.stringify(body, null, 2).slice(0, 500));

    const posts = parseIncomingData(body);

    if (posts.length === 0) {
      return NextResponse.json({
        success: true,
        message: 'No posts to process',
        hint: 'Supported formats: array of posts, {"data": [...]}, {"items": [...]}, single post object'
      });
    }

    const extractedSignals: ExtractedSignal[] = [];
    const processedIds: string[] = [];

    // Process each post
    for (const post of posts) {
      if (!post.content || post.content.length < 5) continue;

      const signal = extractSignal(post);

      if (signal) {
        const { data, error } = await supabaseAdmin
          .from('signals')
          .insert({
            ...signal,
            processed_at: new Date().toISOString()
          })
          .select()
          .single();

        if (!error && data) {
          extractedSignals.push(signal);
          processedIds.push(data.id);
        }
      }
    }

    // Check for urgent alerts
    if (extractedSignals.length > 0) {
      const { data: recentSignals } = await supabaseAdmin
        .from('signals')
        .select('*')
        .order('created_at', { ascending: false })
        .limit(50);

      if (recentSignals) {
        const alertCheck = checkForUrgentAlert(recentSignals as any);

        if (alertCheck.shouldAlert) {
          const matchingIds = recentSignals
            .filter((s: any) =>
              s.part_category === alertCheck.partCategory &&
              s.urgency === 'high_demand'
            )
            .map((s: any) => s.id);

          const { data: existingAlerts } = await supabaseAdmin
            .from('alerts')
            .select('*')
            .eq('part_category', alertCheck.partCategory)
            .eq('is_active', true)
            .gte('created_at', new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString());

          if (!existingAlerts || existingAlerts.length === 0) {
            await supabaseAdmin
              .from('alerts')
              .insert({
                part_category: alertCheck.partCategory,
                vehicle_model: alertCheck.vehicleModel,
                match_count: matchingIds.length,
                signal_ids: matchingIds,
                message: `紧急囤货建议：检测到 ${matchingIds.length} 个帖子在询问 ${alertCheck.partCategory}${alertCheck.vehicleModel ? ` (${alertCheck.vehicleModel})` : ''}`
              });
          }
        }
      }
    }

    return NextResponse.json({
      success: true,
      received: posts.length,
      signals_extracted: extractedSignals.length,
      signals: extractedSignals.map(s => ({
        region: s.region,
        part_category: s.part_category,
        urgency: s.urgency
      }))
    });

  } catch (error) {
    console.error('Error processing raw data:', error);
    return NextResponse.json(
      { error: 'Internal server error', details: String(error) },
      { status: 500 }
    );
  }
}

export async function GET() {
  return NextResponse.json({
    message: 'POST /api/process-raw-data to submit data',
    supportedFormats: [
      'Array of posts: [{"content": "..."}]',
      'Google Search results: {"items": [...]}',
      'Wrapped data: {"data": [...], "posts": [...]}',
      'Single post: {"content": "..."}'
    ]
  });
}
