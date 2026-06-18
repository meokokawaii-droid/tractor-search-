// AI Signal Extraction utilities
// Analyzes raw posts to extract demand signals for agricultural machinery parts

export interface RawPost {
  id?: string;
  content: string;
  author?: string | null;
  location?: string | null;
  timestamp?: string | null;
  source?: string;
  url?: string;
}

export interface ExtractedSignal {
  raw_content: string;
  location: string | null;
  region: string | null;
  vehicle_model: string | null;
  part_category: string | null;
  urgency: 'high_demand' | 'inquiry' | null;
  source: string | null;
  source_id: string | null;
  source_url?: string | null;
  pain_point?: string | null;
  source_type?: 'forum' | 'youtube' | 'news' | 'general_web' | null;
}

// Keywords for filtering tractor-related parts demand
const BRAND_KEYWORDS = ['kubota', '久保田', 'john deere', 'case ih', 'new holland', 'massey ferguson', 'yanmar', '洋马'];
const PARTS_KEYWORDS = [
  'filter', 'seat', 'pump', 'engine', 'transmission', 'hydraulic',
  'belt', 'bearing', 'gasket', 'valve', 'cylinder', 'tire', 'battery',
  'radiator', 'clutch', 'brake', 'steering', 'alternator', 'starter',
  'injector', 'turbo', 'exhaust', 'axle', 'rim', 'hose', 'cable',
  '配件', '滤芯', '座椅', '泵', '发动机', '变速箱', '液压', '轮胎', '电瓶',
  '维修', 'replacement', 'repair', 'parts', 'spare', 'aftermarket', 'oem'
];

// Urgency keywords
const HIGH_DEMAND_KEYWORDS = [
  'urgent', 'immediately', 'asap', 'needed now', '急需', '急购', '立即', '马上',
  'looking for', 'need', 'want to buy', '求购', 'wanted', 'seeking',
  'problem', 'broken', 'failed', 'not working', 'issue', 'trouble'
];
const INQUIRY_KEYWORDS = [
  'asking', 'interested', 'quote', 'price', 'availability', '询问', '询价', '咨询',
  'where to buy', 'how much', 'anyone know', 'recommendation', 'suggestion',
  'which', 'what is', 'how to', 'question', 'help'
];

// Pain point keywords — what's actually wrong with the part
const PAIN_POINT_PATTERNS: Record<string, string[]> = {
  'Leaking': ['leaking', 'leak', 'dripping', '漏油', '漏液'],
  'Worn out': ['worn', 'wear', 'wearing', '磨损'],
  'Broken': ['broken', 'cracked', 'snapped', '断裂', '破裂'],
  'Rusted': ['rust', 'corroded', 'corrosion', '生锈', '腐蚀'],
  'Overheating': ['overheat', 'overheating', 'running hot', '过热'],
  'Noise': ['noisy', 'grinding', 'clunking', '异响', '噪音'],
  'Stuck': ['stuck', 'jammed', 'seized', '卡住', '卡死'],
  'Not starting': ['won\'t start', 'not starting', 'no power', '无法启动'],
  'Slipping': ['slipping', 'slip', '打滑'],
  'Vibration': ['vibration', 'shaking', 'vibrating', '震动'],
};

// Source type detection by URL/domain
const FORUM_DOMAINS = [
  'tractorbynet.com', 'agtalk.net', 'yesterdaystractors.com',
  'reddit.com', 'thefarmingforum.co.uk', 'farmtractoroperator.com',
  'tractorforum.com', 'compacttractorforum.com'
];
const YOUTUBE_DOMAINS = ['youtube.com', 'youtu.be'];
const NEWS_DOMAINS = ['news', 'reuters.com', 'bloomberg.com', 'agripulse.com'];

// Region mapping
const REGION_KEYWORDS: Record<string, string[]> = {
  'Africa': ['africa', 'nigeria', 'kenya', 'ghana', 'tanzania', 'uganda', 'ethiopia', 'south africa', 'african', '尼日利亚', '肯尼亚', '加纳', '非洲'],
  'Southeast Asia': ['thailand', 'vietnam', 'indonesia', 'malaysia', 'philippines', 'myanmar', 'cambodia', 'laos', 'singapore', '东南亚', '泰国', '越南', '印尼', '马来西亚'],
  'South Asia': ['india', 'pakistan', 'bangladesh', 'sri lanka', 'nepal', 'indian', '印度', '巴基斯坦'],
  'Middle East': ['dubai', 'saudi', 'iran', 'iraq', 'egypt', 'middle east', 'uae', '中东', '迪拜'],
  'Latin America': ['brazil', 'mexico', 'argentina', 'colombia', 'peru', 'chile', 'latin america', '南美', '巴西', '墨西哥'],
  'Europe': ['germany', 'france', 'spain', 'italy', 'uk', 'europe', 'european', '欧洲', '德国', '法国'],
  'North America': ['usa', 'canada', 'america', 'united states', 'north america', '美国', '加拿大'],
  'East Asia': ['japan', 'korea', 'taiwan', 'china', 'chinese', '日本', '韩国', '台湾', '中国']
};

// Vehicle model patterns — multi-brand
const VEHICLE_MODEL_PATTERNS = [
  /kubota\s*(\w+[\w-]*)/gi,
  /(L\s*\d{3,4})/gi,
  /(M\s*\d{3,4})/gi,
  /(B\s*\d{3,4})/gi,
  /(Kubota\s*\d+)/gi,
  /john\s*deere\s*(\d{3,4}[A-Z]?)/gi,
  /case\s*(IH\s*)?(\d{3,4})/gi,
  /new\s*holland\s*(\w+[\w-]*)/gi,
  /massey\s*ferguson\s*(\d{3,4})/gi,
  /yanmar\s*(\w+[\w-]*)/gi,
];

// Brand names for generic model detection
const BRAND_NAMES = ['kubota', 'john deere', 'case ih', 'case', 'new holland', 'massey ferguson', 'yanmar'];

// Supplier / B2B blacklist — these indicate the source is a seller, not a buyer
const SUPPLIER_KEYWORDS = [
  // B2B platform language
  'for sale', 'supplier', 'manufacturer', 'wholesale', 'price list',
  'distributor', 'exporter', 'factory', 'oem supplier', 'bulk',
  'cheap price', 'competitive price', 'contact us for quote',
  'we supply', 'we sell', 'our products', 'catalog',
  // E-commerce / independent shop language
  'add to cart', 'add to basket', 'checkout', 'free shipping',
  'fast delivery', 'same day shipping', 'order today', 'ship today',
  'secure payment', 'money back', 'guarantee', 'limited time offer',
  'shop now', 'buy online', 'order now', 'in stock', 'inventory',
  'best price', 'lowest price', 'discount', 'save up to', 'off retail',
  'customer reviews', 'rated', 'best seller', 'top seller',
  'subscribe and save', 'free returns', 'easy returns'
];

// Price pattern — catches "$299", "$1,299.00", "¥5000", etc.
const PRICE_PATTERN = /\$\s?\d{1,3}(,\d{3})*(\.\d{2})?|\¥\s?\d+/;

const SUPPLIER_DOMAINS = [
  // B2B marketplaces
  'alibaba.com', 'made-in-china.com', 'ec21.com', 'tradekey.com',
  'globalsources.com', 'diytrade.com', 'b2brazil.com', 'indiamart.com',
  'thomasnet.com', 'kompass.com', 'ecplaza.net',
  // Independent tractor parts shops
  'tractorsupply.com', 'messicks.com', 'kubotaparts.com',
  'kubotapartsdirect.com', 'colemanequip.com', 'brokentractor.com',
  'allstatesagparts.com', 'stablexports.com', 'valleypower.com',
  'jptractors.com', 'kubotapartsonline.com', 'affordabletractorsupply.com',
  'tractorpartsasap.com', 'kubotapartswarehouse.com', 'departs.com',
  'jdpartslive.com', 'greenfarmparts.com', 'shopparts.uaoparts.com',
  // Amazon / eBay listings
  'amazon.com', 'ebay.com', 'walmart.com', 'etsy.com',
  // Chinese cross-border sellers
  'dhgate.com', 'aliexpress.com', 'banggood.com', 'gearbest.com',
  'lightinthebox.com', 'tomtop.com'
];

function isSupplierContent(content: string, url?: string | null): boolean {
  const lowerContent = content.toLowerCase();

  // Check supplier keywords in content
  const hasSupplierKeyword = SUPPLIER_KEYWORDS.some(kw =>
    lowerContent.includes(kw.toLowerCase())
  );
  if (hasSupplierKeyword) return true;

  // Check price pattern — e-commerce product pages almost always show prices
  if (PRICE_PATTERN.test(content)) return true;

  // Check supplier domains in URL
  if (url) {
    const lowerUrl = url.toLowerCase();
    const hasSupplierDomain = SUPPLIER_DOMAINS.some(domain =>
      lowerUrl.includes(domain)
    );
    if (hasSupplierDomain) return true;
  }

  return false;
}

export function extractSignal(post: RawPost): ExtractedSignal | null {
  const content = post.content.toLowerCase();

  // Check if post contains any tractor brand keyword
  const hasBrand = BRAND_KEYWORDS.some(keyword =>
    content.includes(keyword.toLowerCase())
  );

  if (!hasBrand) return null;

  // Check if post contains parts demand keywords
  const hasPartsDemand = PARTS_KEYWORDS.some(keyword =>
    content.includes(keyword.toLowerCase())
  );

  if (!hasPartsDemand) return null;

  // Filter out supplier/B2B content — we want buyers, not sellers
  if (isSupplierContent(post.content, post.url)) {
    return null;
  }

  // Extract region
  const region = detectRegion(content, post.location);

  // Extract vehicle model
  const vehicleModel = extractVehicleModel(post.content);

  // Extract part category
  const partCategory = extractPartCategory(content);

  // Determine urgency
  const urgency = determineUrgency(content);

  // Extract pain point
  const painPoint = extractPainPoint(content);

  // Detect source type from URL
  const sourceType = detectSourceType(post.url);

  return {
    raw_content: post.content,
    location: post.location || null,
    region,
    vehicle_model: vehicleModel,
    part_category: partCategory,
    urgency,
    source: post.source || 'unknown',
    source_id: post.id || null,
    source_url: post.url || null,
    pain_point: painPoint,
    source_type: sourceType,
  };
}

function detectRegion(content: string, explicitLocation?: string | null): string | null {
  const searchText = (content + ' ' + (explicitLocation || '')).toLowerCase();

  for (const [region, keywords] of Object.entries(REGION_KEYWORDS)) {
    if (keywords.some(keyword => searchText.includes(keyword.toLowerCase()))) {
      return region;
    }
  }

  return 'Unknown';
}

function extractVehicleModel(content: string): string | null {
  for (const pattern of VEHICLE_MODEL_PATTERNS) {
    const matches = content.match(pattern);
    if (matches && matches.length > 0) {
      return matches[0].trim();
    }
  }

  // Check for generic brand mentions
  const lowerContent = content.toLowerCase();
  for (const brand of BRAND_NAMES) {
    if (lowerContent.includes(brand)) {
      return `${brand.charAt(0).toUpperCase() + brand.slice(1)} (unspecified model)`;
    }
  }

  return null;
}

function extractPartCategory(content: string): string | null {
  const lowerContent = content.toLowerCase();

  for (const part of PARTS_KEYWORDS) {
    if (lowerContent.includes(part.toLowerCase())) {
      // Map to normalized category names
      const categoryMap: Record<string, string> = {
        'filter': 'Filter',
        '滤芯': 'Filter',
        'seat': 'Seat',
        '座椅': 'Seat',
        'pump': 'Pump',
        '泵': 'Pump',
        'engine': 'Engine',
        '发动机': 'Engine',
        'transmission': 'Transmission',
        '变速箱': 'Transmission',
        'hydraulic': 'Hydraulic System',
        '液压': 'Hydraulic System',
        'belt': 'Belt',
        'bearing': 'Bearing',
        'gasket': 'Gasket',
        'valve': 'Valve',
        'cylinder': 'Cylinder',
        'tire': 'Tire',
        'battery': 'Battery'
      };

      return categoryMap[part.toLowerCase()] || part.charAt(0).toUpperCase() + part.slice(1);
    }
  }

  return 'Other Parts';
}

function determineUrgency(content: string): 'high_demand' | 'inquiry' {
  const lowerContent = content.toLowerCase();

  // Check for high demand indicators
  const hasHighDemand = HIGH_DEMAND_KEYWORDS.some(keyword =>
    lowerContent.includes(keyword.toLowerCase())
  );

  if (hasHighDemand) return 'high_demand';

  // Check for inquiry indicators
  const hasInquiry = INQUIRY_KEYWORDS.some(keyword =>
    lowerContent.includes(keyword.toLowerCase())
  );

  if (hasInquiry) return 'inquiry';

  // Default to inquiry if mentioning parts
  return 'inquiry';
}

function extractPainPoint(content: string): string | null {
  const lowerContent = content.toLowerCase();

  for (const [painPoint, keywords] of Object.entries(PAIN_POINT_PATTERNS)) {
    if (keywords.some(kw => lowerContent.includes(kw.toLowerCase()))) {
      return painPoint;
    }
  }

  return null;
}

function detectSourceType(url?: string | null): 'forum' | 'youtube' | 'news' | 'general_web' | null {
  if (!url) return null;

  const lowerUrl = url.toLowerCase();

  if (FORUM_DOMAINS.some(d => lowerUrl.includes(d))) return 'forum';
  if (YOUTUBE_DOMAINS.some(d => lowerUrl.includes(d))) return 'youtube';
  if (NEWS_DOMAINS.some(d => lowerUrl.includes(d))) return 'news';

  return 'general_web';
}

export function checkForUrgentAlert(signals: ExtractedSignal[]): {
  shouldAlert: boolean;
  partCategory: string | null;
  vehicleModel: string | null;
  matchingSignals: ExtractedSignal[];
} {
  // Group signals by part category + vehicle model
  const grouped = new Map<string, ExtractedSignal[]>();

  for (const signal of signals) {
    if (!signal.part_category || signal.urgency !== 'high_demand') continue;

    const key = `${signal.part_category}|||${signal.vehicle_model || 'any'}`;
    const existing = grouped.get(key) || [];
    existing.push(signal);
    grouped.set(key, existing);
  }

  // Find groups with 3+ signals (same seat model, urgent need)
  for (const [key, group] of grouped.entries()) {
    if (group.length >= 3) {
      const [partCategory, vehicleModel] = key.split('|||');
      return {
        shouldAlert: true,
        partCategory,
        vehicleModel: vehicleModel === 'any' ? null : vehicleModel,
        matchingSignals: group
      };
    }
  }

  return {
    shouldAlert: false,
    partCategory: null,
    vehicleModel: null,
    matchingSignals: []
  };
}
