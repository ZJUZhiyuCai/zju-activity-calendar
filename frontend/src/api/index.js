// 浙大活动日历 - API 服务层
import dayjs from 'dayjs';

const API_BASE = import.meta.env.VITE_API_BASE || '/api/v1/wx';

// 学院分类颜色映射
export const COLLEGE_COLORS = {
  // 人文社科
  '文学院': 'var(--college-humanities)',
  '历史学院': 'var(--college-humanities)',
  '哲学学院': 'var(--college-humanities)',
  '外国语学院': 'var(--college-humanities)',
  '传媒与国际文化学院': 'var(--college-humanities)',
  '艺术与考古学院': 'var(--college-humanities)',
  '经济学院': 'var(--college-management)',
  '光华法学院': 'var(--college-humanities)',
  '教育学院': 'var(--college-humanities)',
  '管理学院': 'var(--college-management)',
  '公共管理学院': 'var(--college-management)',
  '社会学系': 'var(--college-humanities)',
  '马克思主义学院': 'var(--college-humanities)',

  // 理学
  '数学科学学院': 'var(--college-science)',
  '物理学院': 'var(--college-science)',
  '化学系': 'var(--college-science)',
  '地球科学学院': 'var(--college-science)',
  '心理与行为科学系': 'var(--college-science)',

  // 工学
  '机械工程学院': 'var(--college-engineering)',
  '材料科学与工程学院': 'var(--college-engineering)',
  '能源工程学院': 'var(--college-engineering)',
  '电气工程学院': 'var(--college-engineering)',
  '建筑工程学院': 'var(--college-engineering)',
  '化学工程与生物工程学院': 'var(--college-engineering)',
  '海洋学院': 'var(--college-science)',
  '航空航天学院': 'var(--college-engineering)',
  '光电科学与工程学院': 'var(--college-engineering)',
  '信息与电子工程学院': 'var(--college-engineering)',
  '控制科学与工程学院': 'var(--college-engineering)',
  '计算机科学与技术学院': 'var(--college-engineering)',
  '软件学院': 'var(--college-engineering)',
  '生物医学工程与仪器科学学院': 'var(--college-medical)',
  '集成电路学院': 'var(--college-engineering)',
  '人工智能学院': 'var(--college-engineering)',
  '生命科学学院': 'var(--college-medical)',
  '生物系统工程与食品科学学院': 'var(--college-engineering)',
  '环境与资源学院': 'var(--college-engineering)',
  '农业与生物技术学院': 'var(--college-engineering)',
  '动物科学学院': 'var(--college-engineering)',

  // 医学
  '医学院': 'var(--college-medical)',
  '药学院': 'var(--college-medical)',
  '基础医学系': 'var(--college-medical)',

  // 校级平台
  '图书馆讲座': 'var(--morandi-blue)',
  '研究生院': 'var(--morandi-blue)',
  '本科生院': 'var(--morandi-blue)',
  '研究生活动': 'var(--morandi-blue)',
  '国际教育学院': 'var(--morandi-blue)',
  '图书馆': 'var(--morandi-blue)',

  // 默认
  'default': 'var(--morandi-blue)'
};

// 获取学院颜色
export function getCollegeColor(collegeName) {
  return COLLEGE_COLORS[collegeName] || COLLEGE_COLORS['default'];
}

const CAMPUS_PATTERNS = [
  ['紫金港', '紫金港'],
  ['玉泉', '玉泉'],
  ['西溪', '西溪'],
  ['华家池', '华家池'],
  ['之江', '之江'],
  ['海宁', '海宁'],
];

export function extractCampus(location) {
  const text = location || '';
  const matched = CAMPUS_PATTERNS.find(([pattern]) => text.includes(pattern));
  return matched ? matched[1] : null;
}

export function getActivityCampus(activity) {
  return activity.campus || extractCampus(activity.location);
}

function getTimeWeight(activityDate) {
  const today = dayjs().startOf('day');
  const target = dayjs(activityDate).startOf('day');
  const distance = target.diff(today, 'day');

  if (distance < 0) return -8;
  if (distance === 0) return 8;
  if (distance === 1) return 7;
  if (distance <= 3) return 5;
  if (distance <= 7) return 3;
  return 1;
}

export function getRelevanceScore(activity, selectedCollege = 'all') {
  let score = getTimeWeight(activity.activity_date);

  if (selectedCollege !== 'all' && activity.college_id === selectedCollege) {
    score += 4;
  }

  if (activity.source_type === 'core') {
    score += 4;
  }

  if (['library', 'undergraduate_school', 'international_college'].includes(activity.college_id)) {
    score += 3;
  }

  if (activity.activity_time) {
    score += 2;
  }

  if (activity.location) {
    score += 2;
  }

  if (activity.speaker) {
    score += 1;
  }

  const previewText = `${activity.title} ${activity.description || ''}`.toLowerCase();
  if (/(求真一小时|讲坛|讲堂|论坛|分享会|career|guide|训练营|人工智能|大模型)/i.test(previewText)) {
    score += 1;
  }

  if (/(研究生)/i.test(previewText)) {
    score -= 1;
  }

  return score;
}

// 学院列表
export const COLLEGES = [
  { id: 'all', name: '全部学院', count: 0 },
  { id: 'library', name: '图书馆讲座', category: 'core' },
  { id: 'graduate_school', name: '研究生院', category: 'core' },
  { id: 'undergraduate_school', name: '本科生院', category: 'core' },
  { id: 'graduate_calendar', name: '研究生活动', category: 'core' },
  { id: 'international_college', name: '国际教育学院', category: 'core' },
  // 人文社科
  { id: 'lit', name: '文学院', category: 'humanities' },
  { id: 'cec', name: '经济学院', category: 'humanities' },
  { id: 'som', name: '管理学院', category: 'humanities' },
  { id: 'ghls', name: '光华法学院', category: 'humanities' },
  { id: 'ced', name: '教育学院', category: 'humanities' },
  { id: 'cmic', name: '传媒学院', category: 'humanities' },
  // 理学
  { id: 'math', name: '数学学院', category: 'science' },
  { id: 'physics', name: '物理学院', category: 'science' },
  { id: 'chem', name: '化学系', category: 'science' },
  // 工学
  { id: 'cs', name: '计算机学院', category: 'engineering' },
  { id: 'cst', name: '软件学院', category: 'engineering' },
  { id: 'ai', name: '人工智能学院', category: 'engineering' },
  { id: 'ee', name: '电气学院', category: 'engineering' },
  { id: 'me', name: '机械学院', category: 'engineering' },
  { id: 'opt', name: '光电学院', category: 'engineering' },
  { id: 'cls', name: '生命学院', category: 'engineering' },
  { id: 'ers', name: '环资学院', category: 'engineering' },
  // 医学
  { id: 'cmm', name: '医学院', category: 'medical' },
  { id: 'pharma', name: '药学院', category: 'medical' },
];

// API 请求函数
export const api = {
  // 获取活动列表
  async getActivities(params = {}) {
    const {
      start_date,
      end_date,
      college_id,
      keyword,
      student_view,
      sort_by,
      upcoming_only,
      page = 1,
      limit = 100
    } = params;

    const queryParams = new URLSearchParams({
      page: page.toString(),
      limit: limit.toString(),
    });

    if (start_date) queryParams.append('start_date', start_date);
    if (end_date) queryParams.append('end_date', end_date);
    if (college_id && college_id !== 'all') queryParams.append('college_id', college_id);
    if (keyword) queryParams.append('keyword', keyword);
    if (student_view) queryParams.append('student_view', 'true');
    if (sort_by) queryParams.append('sort_by', sort_by);
    if (upcoming_only) queryParams.append('upcoming_only', 'true');

    const response = await fetch(`${API_BASE}/activities?${queryParams}`);
    if (!response.ok) throw new Error('获取活动列表失败');

    return response.json();
  },

  // 获取单个活动详情
  async getActivityDetail(id) {
    const response = await fetch(`${API_BASE}/activities/${id}`);
    if (!response.ok) throw new Error('获取活动详情失败');

    return response.json();
  },

  // 获取学院列表
  async getColleges() {
    const response = await fetch(`${API_BASE}/colleges`);
    if (!response.ok) throw new Error('获取学院列表失败');

    return response.json();
  },

  // 搜索活动
  async searchActivities(keyword) {
    const response = await fetch(`${API_BASE}/activities/search?q=${encodeURIComponent(keyword)}`);
    if (!response.ok) throw new Error('搜索失败');

    return response.json();
  }
};

// 模拟数据（开发阶段使用）
export const mockActivities = [
  {
    id: '1',
    title: '人工智能前沿技术讲座：大模型时代的技术变革',
    college_id: 'cs',
    college_name: '计算机科学与技术学院',
    activity_type: '讲座',
    speaker: '张明教授',
    speaker_title: '浙江大学计算机学院教授、博士生导师',
    speaker_intro: '研究方向为人工智能、机器学习，在顶会发表论文50余篇。',
    activity_date: '2026-04-05',
    activity_time: '14:00-16:00',
    location: '紫金港校区蒙民伟楼250报告厅',
    organizer: '浙江大学计算机科学与技术学院',
    description: '本次讲座将深入探讨大语言模型的技术原理、应用场景及未来发展趋势，分享最新的研究成果和实践经验。欢迎感兴趣的师生参加！',
    cover_image: null,
    source_url: 'https://cs.zju.edu.cn/',
    registration_required: false,
    registration_link: null
  },
  {
    id: '2',
    title: '数字经济与企业创新管理论坛',
    college_id: 'som',
    college_name: '管理学院',
    activity_type: '论坛',
    speaker: '李华教授',
    speaker_title: '长江学者、管理学院院长',
    speaker_intro: '专注于企业战略管理与创新研究。',
    activity_date: '2026-04-05',
    activity_time: '09:00-12:00',
    location: '紫金港校区管理学院报告厅',
    organizer: '浙江大学管理学院',
    description: '邀请业界专家与学者共同探讨数字经济时代企业的创新战略与管理实践。',
    cover_image: null,
    source_url: 'https://som.zju.edu.cn/',
    registration_required: true,
    registration_link: 'https://som.zju.edu.cn/register'
  },
  {
    id: '3',
    title: '量子计算前沿进展学术报告',
    college_id: 'physics',
    college_name: '物理学院',
    activity_type: '学术报告',
    speaker: '王强院士',
    speaker_title: '中国科学院院士',
    speaker_intro: '量子物理领域国际知名专家。',
    activity_date: '2026-04-07',
    activity_time: '15:00-17:00',
    location: '玉泉校区教七-301',
    organizer: '浙江大学物理学院',
    description: '介绍量子计算最新研究进展，探讨量子优势的实现路径。',
    cover_image: null,
    source_url: 'https://physics.zju.edu.cn/',
    registration_required: false,
    registration_link: null
  },
  {
    id: '4',
    title: '医学影像AI诊断技术研讨会',
    college_id: 'cmm',
    college_name: '医学院',
    activity_type: '研讨会',
    speaker: '陈医生',
    speaker_title: '浙大附属第一医院影像科主任',
    speaker_intro: '从事医学影像诊断20年，AI辅助诊断领域专家。',
    activity_date: '2026-04-08',
    activity_time: '10:00-12:00',
    location: '华家池校区医学中心',
    organizer: '浙江大学医学院',
    description: '探讨AI技术在医学影像诊断中的应用现状与未来发展。',
    cover_image: null,
    source_url: 'https://cmm.zju.edu.cn/',
    registration_required: false,
    registration_link: null
  },
  {
    id: '5',
    title: 'Word排版方法与技巧讲座',
    college_id: 'library',
    college_name: '图书馆',
    activity_type: '培训讲座',
    speaker: '图书馆培训部',
    speaker_title: '浙江大学图书馆',
    speaker_intro: '',
    activity_date: '2026-04-10',
    activity_time: '14:00-15:30',
    location: '紫金港校区图书馆一楼培训室',
    organizer: '浙江大学图书馆',
    description: '系统讲解Word文档排版的实用技巧，提升论文写作效率。',
    cover_image: null,
    source_url: 'https://libweb.zju.edu.cn/',
    registration_required: true,
    registration_link: 'https://libweb.zju.edu.cn/register'
  },
  {
    id: '6',
    title: '经济学前沿：行为经济学视角下的消费决策',
    college_id: 'cec',
    college_name: '经济学院',
    activity_type: '讲座',
    speaker: '刘教授',
    speaker_title: '经济学院副教授',
    speaker_intro: '行为经济学研究专家。',
    activity_date: '2026-04-11',
    activity_time: '13:30-15:30',
    location: '紫金港校区经济学院报告厅',
    organizer: '浙江大学经济学院',
    description: '从行为经济学角度分析消费者的决策行为与心理机制。',
    cover_image: null,
    source_url: 'https://cec.zju.edu.cn/',
    registration_required: false,
    registration_link: null
  },
  {
    id: '7',
    title: '新能源汽车技术发展趋势',
    college_id: 'me',
    college_name: '机械工程学院',
    activity_type: '讲座',
    speaker: '周工程师',
    speaker_title: '比亚迪首席技术官',
    speaker_intro: '新能源汽车动力系统专家。',
    activity_date: '2026-04-15',
    activity_time: '14:00-16:00',
    location: '紫金港校区机械学院大楼',
    organizer: '浙江大学机械工程学院',
    description: '分享新能源汽车行业的最新技术发展与未来趋势。',
    cover_image: null,
    source_url: 'https://me.zju.edu.cn/',
    registration_required: false,
    registration_link: null
  },
  {
    id: '8',
    title: '古典文学与现代人生',
    college_id: 'lit',
    college_name: '文学院',
    activity_type: '讲座',
    speaker: '王教授',
    speaker_title: '文学院资深教授',
    speaker_intro: '古典文学研究学者。',
    activity_date: '2026-04-18',
    activity_time: '19:00-21:00',
    location: '紫金港校区人文学院报告厅',
    organizer: '浙江大学文学院',
    description: '探讨古典文学作品对现代人生的启示与价值。',
    cover_image: null,
    source_url: 'https://lit.zju.edu.cn/',
    registration_required: false,
    registration_link: null
  },
  {
    id: '9',
    title: 'Excel数据处理与分析培训',
    college_id: 'library',
    college_name: '图书馆',
    activity_type: '培训讲座',
    speaker: '图书馆培训部',
    speaker_title: '浙江大学图书馆',
    speaker_intro: '',
    activity_date: '2026-04-20',
    activity_time: '14:00-16:00',
    location: '紫金港校区图书馆一楼培训室',
    organizer: '浙江大学图书馆',
    description: '学习Excel数据处理的高级技巧，提升数据分析能力。',
    cover_image: null,
    source_url: 'https://libweb.zju.edu.cn/',
    registration_required: true,
    registration_link: 'https://libweb.zju.edu.cn/register'
  },
  {
    id: '10',
    title: '人工智能与医疗健康',
    college_id: 'ai',
    college_name: '人工智能学院',
    activity_type: '讲座',
    speaker: '张院士',
    speaker_title: '中国工程院院士',
    speaker_intro: 'AI医疗领域开拓者。',
    activity_date: '2026-04-22',
    activity_time: '10:00-12:00',
    location: '紫金港校区人工智能学院报告厅',
    organizer: '浙江大学人工智能学院',
    description: '探讨人工智能在医疗健康领域的创新应用。',
    cover_image: null,
    source_url: 'https://ai.zju.edu.cn/',
    registration_required: false,
    registration_link: null
  }
];

// 按日期分组活动
export function groupActivitiesByDate(activities) {
  const grouped = {};
  activities.forEach(activity => {
    const date = activity.activity_date;
    if (!grouped[date]) {
      grouped[date] = [];
    }
    grouped[date].push(activity);
  });
  return grouped;
}

// 格式化预览日期显示
export function formatPreviewDate(date) {
  const d = dayjs(date).startOf('day');
  const today = dayjs().startOf('day');
  
  if (d.isSame(today, 'day')) return '今天';
  if (d.isSame(today.add(1, 'day'), 'day')) return '明天';
  if (d.isSame(today.add(2, 'day'), 'day')) return '后天';
  
  return d.format('M月D日');
}

// 获取月份的天数
export function getDaysInMonth(year, month) {
  return dayjs(`${year}-${month}`).daysInMonth();
}

// 获取月份第一天是星期几
export function getFirstDayOfMonth(year, month) {
  return dayjs(`${year}-${month}-01`).day();
}

// 格式化日期显示
export function formatDate(date, format = 'YYYY-MM-DD') {
  return dayjs(date).format(format);
}

// 判断是否是今天
export function isToday(date) {
  return dayjs(date).isSame(dayjs(), 'day');
}

// 判断是否是同一天
export function isSameDay(date1, date2) {
  return dayjs(date1).isSame(dayjs(date2), 'day');
}
