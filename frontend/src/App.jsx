// 浙大活动日历 - 主应用
import { useState, useEffect, useMemo, useDeferredValue } from 'react';
import dayjs from 'dayjs';
import {
  Calendar,
  Header,
  CollegeFilter,
  ActivityDetail,
  StatsCards,
  PreviewRail,
  Hero,
} from './components';
import { mockActivities, api, COLLEGES } from './api';
import {
  getInitialSelectedDate,
  resolveActivityFeedState,
} from './lib/activityState';
import './styles/global.css';

const CATEGORY_MAP = {
  core: 'core',
  humanities: 'humanities',
  science: 'science',
  engineering: 'engineering',
  medical: 'medical',
  '人文社科': 'humanities',
  '理学': 'science',
  '工学': 'engineering',
  '医学': 'medical',
};

const ALLOW_DEMO_FALLBACK = import.meta.env.DEV || import.meta.env.VITE_ENABLE_DEMO_FALLBACK === 'true';

function normalizeColleges(colleges) {
  const base = Array.isArray(colleges) ? colleges : [];
  const normalized = base
    .filter(c => c.id !== 'all')
    .map((college) => ({
      ...college,
      category: CATEGORY_MAP[college.category] || (college.source_type === 'core' ? 'core' : 'engineering'),
    }));

  return [{ id: 'all', name: '全部学院', category: 'all' }, ...normalized];
}

function App() {
  // 状态管理
  const [theme, setTheme] = useState(() => {
    const saved = localStorage.getItem('theme');
    return saved || 'light';
  });

  const [colleges, setColleges] = useState(COLLEGES);
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [selectedCollege, setSelectedCollege] = useState('all');
  const [selectedDate, setSelectedDate] = useState(null);
  const [previewMode, setPreviewMode] = useState('relevant');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedActivity, setSelectedActivity] = useState(null);
  const [dataNotice, setDataNotice] = useState(null);
  const deferredQuery = useDeferredValue(searchQuery);

  // 初始化主题
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }, [theme]);

  // 加载数据
  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      try {
        const [activitiesResult, collegesResult] = await Promise.allSettled([
          api.getActivities({
            page: 1,
            limit: 500,
            start_date: dayjs().startOf('month').format('YYYY-MM-DD'),
            student_view: true,
            sort_by: 'relevance',
          }),
          api.getColleges(),
        ]);

        let activitiesData = [];
        let nextNotice = null;

        if (activitiesResult.status === 'fulfilled') {
          const payload = activitiesResult.value?.data ?? activitiesResult.value;
          activitiesData = payload;
        }

        const resolvedState = resolveActivityFeedState({
          payload: activitiesData,
          status: activitiesResult.status,
          allowDemoFallback: ALLOW_DEMO_FALLBACK,
          mockActivities,
          now: dayjs(),
        });
        const resolvedActivities = resolvedState.activities;
        nextNotice = resolvedState.notice;

        setActivities(resolvedActivities);
        setSelectedDate(getInitialSelectedDate(resolvedActivities));
        setDataNotice(nextNotice);

        if (collegesResult.status === 'fulfilled') {
          const payload = collegesResult.value?.data ?? collegesResult.value;
          setColleges(normalizeColleges(payload));
        } else {
          setColleges(normalizeColleges(COLLEGES));
        }
      } catch (error) {
        console.error('加载数据失败:', error);
        if (ALLOW_DEMO_FALLBACK) {
          const resolvedMock = resolveActivityFeedState({
            payload: null,
            status: 'rejected',
            allowDemoFallback: true,
            mockActivities,
            now: dayjs(),
          }).activities;
          setActivities(resolvedMock);
          setColleges(normalizeColleges(COLLEGES));
          setSelectedDate(getInitialSelectedDate(resolvedMock));
          setDataNotice(resolveActivityFeedState({
            payload: null,
            status: 'rejected',
            allowDemoFallback: true,
            mockActivities,
            now: dayjs(),
          }).notice);
        } else {
          setActivities([]);
          setColleges(normalizeColleges(COLLEGES));
          setSelectedDate(dayjs().format('YYYY-MM-DD'));
          setDataNotice({
            tone: 'error',
            title: '活动服务加载失败',
            message: '发生未知错误，当前未展示演示数据，请检查后端服务或稍后重试。',
          });
        }
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, []);

  // 过滤活动
  const filteredActivities = useMemo(() => {
    let result = activities;

    if (selectedCollege !== 'all') {
      result = result.filter(a => a.college_id === selectedCollege);
    }

    if (deferredQuery.trim()) {
      const query = deferredQuery.toLowerCase();
      result = result.filter(a =>
        a.title.toLowerCase().includes(query) ||
        a.speaker?.toLowerCase().includes(query) ||
        a.college_name?.toLowerCase().includes(query) ||
        a.location?.toLowerCase().includes(query)
      );
    }

    return result;
  }, [activities, selectedCollege, deferredQuery]);

  // 切换主题
  const toggleTheme = () => {
    setTheme(prev => prev === 'light' ? 'dark' : 'light');
  };

  const openActivityDetail = async (activity) => {
    setSelectedActivity(activity);
    setDetailLoading(true);

    try {
      const response = await api.getActivityDetail(activity.id);
      const payload = response?.data ?? response;

      if (payload && payload.id === activity.id) {
        setSelectedActivity((current) => current?.id === activity.id ? { ...current, ...payload } : current);
      }
    } catch (error) {
      console.error('加载活动详情失败:', error);
    } finally {
      setDetailLoading(false);
    }
  };

  const closeActivityDetail = () => {
    setSelectedActivity(null);
    setDetailLoading(false);
  };

  const handleDateSelect = (date) => {
    setSelectedDate(date);
    setPreviewMode('selected');
  };

  return (
    <div className="app-container">
      <Header
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        theme={theme}
        onThemeToggle={toggleTheme}
      />

      <main className="main-content">
        <div className="discovery-area" style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <Hero 
            activities={filteredActivities} 
            onActivityClick={openActivityDetail} 
          />

          <CollegeFilter
            selectedCollege={selectedCollege}
            onCollegeSelect={setSelectedCollege}
            colleges={colleges}
            activities={activities}
          />

          <StatsCards activities={filteredActivities} />

          {dataNotice && (
            <div className={`data-notice ${dataNotice.tone || ''}`}>
              <div className="data-notice-title">{dataNotice.title}</div>
              <div className="data-notice-copy">{dataNotice.message}</div>
              {dataNotice.meta?.generatedAt && (
                <div className="data-notice-copy">
                  最近状态生成时间：{dayjs(dataNotice.meta.generatedAt).format('MM-DD HH:mm')}
                </div>
              )}
              {dataNotice.meta?.lastSuccessSyncAt && (
                <div className="data-notice-copy">
                  最近成功同步时间：{dayjs(dataNotice.meta.lastSuccessSyncAt).format('MM-DD HH:mm')}
                </div>
              )}
            </div>
          )}

          {loading ? (
            <div className="loading">
              <div className="loading-spinner" />
            </div>
          ) : (
            <Calendar
              key={selectedDate ? selectedDate.slice(0, 7) : 'calendar-current'}
              activities={filteredActivities}
              selectedDate={selectedDate}
              onDateSelect={handleDateSelect}
              onActivityClick={openActivityDetail}
            />
          )}
        </div>

        <PreviewRail
          activities={filteredActivities}
          selectedDate={selectedDate}
          previewMode={previewMode}
          onPreviewModeChange={setPreviewMode}
          onActivityClick={openActivityDetail}
          selectedCollege={selectedCollege}
        />
      </main>

      <ActivityDetail
        activity={selectedActivity}
        loading={detailLoading}
        onClose={closeActivityDetail}
      />
    </div>
  );
}

export default App;
