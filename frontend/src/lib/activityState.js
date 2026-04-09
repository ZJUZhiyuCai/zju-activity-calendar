import dayjs from 'dayjs';

export function sortActivities(list) {
  return [...list].sort((left, right) => {
    if ((left.activity_date || '') !== (right.activity_date || '')) {
      return (left.activity_date || '').localeCompare(right.activity_date || '');
    }
    return (left.activity_time || '').localeCompare(right.activity_time || '');
  });
}

export function hasUpcomingActivities(list, now = dayjs()) {
  const today = now.format('YYYY-MM-DD');
  return list.some((activity) => (activity.activity_date || '') >= today);
}

export function getInitialSelectedDate(list, now = dayjs()) {
  const sorted = sortActivities(list);
  const today = now.format('YYYY-MM-DD');
  const nextUpcoming = sorted.find((activity) => (activity.activity_date || '') >= today);
  return nextUpcoming?.activity_date || sorted[0]?.activity_date || today;
}

export function buildStatusNotice({ tone = 'info', title, message, meta }) {
  return { tone, title, message, meta };
}

export function summarizeSourceStatus(sourceStatus) {
  if (!sourceStatus) return null;
  return {
    total: sourceStatus.total_sources || 0,
    ok: sourceStatus.ok_sources || 0,
    error: sourceStatus.error_sources || 0,
    generatedAt: sourceStatus.generated_at || null,
    lastSuccessSyncAt: sourceStatus.last_success_sync_at || null,
  };
}

export function buildFreshnessNotice(payload, sourceSummary) {
  const freshness = payload?.freshness;

  if (freshness === 'degraded') {
    return buildStatusNotice({
      tone: 'error',
      title: '数据来源当前不可用',
      message: `已尝试 ${sourceSummary.total} 个来源，但暂未拿到可用结果。请检查来源状态或稍后重试。`,
      meta: sourceSummary,
    });
  }

  if (freshness === 'partial') {
    return buildStatusNotice({
      tone: 'warning',
      title: '已连接真实数据，但部分来源失败',
      message: `已尝试 ${sourceSummary.total} 个来源，成功 ${sourceSummary.ok} 个，失败 ${sourceSummary.error} 个。`,
      meta: sourceSummary,
    });
  }

  if (freshness === 'empty') {
    return buildStatusNotice({
      tone: 'warning',
      title: '当前暂无可展示活动',
      message: '后端已返回真实结果，但当前没有满足条件的未来活动。',
      meta: sourceSummary,
    });
  }

  if (freshness === 'cold') {
    return buildStatusNotice({
      tone: 'warning',
      title: '数据服务刚启动',
      message: '后端已连接，但当前还没有完成一次可见的数据聚合。',
      meta: sourceSummary,
    });
  }

  return buildStatusNotice({
    tone: 'info',
    title: '已连接真实活动数据',
    message: `已尝试 ${sourceSummary.total} 个来源，成功 ${sourceSummary.ok} 个，失败 ${sourceSummary.error} 个。`,
    meta: sourceSummary,
  });
}

export function resolveActivityFeedState({
  payload,
  status,
  allowDemoFallback,
  mockActivities,
  now = dayjs(),
}) {
  const activitiesData = Array.isArray(payload) ? payload : (payload?.list ?? []);
  const sourceSummary = summarizeSourceStatus(payload?.source_status);
  let notice = sourceSummary ? buildFreshnessNotice(payload, sourceSummary) : null;
  let activities = sortActivities(activitiesData);

  if (status === 'rejected') {
    if (allowDemoFallback) {
      return {
        activities: sortActivities(mockActivities),
        notice: buildStatusNotice({
          tone: 'demo',
          title: '当前使用演示数据',
          message: '获取数据失败，使用演示数据继续验证体验。',
        }),
      };
    }

    return {
      activities: [],
      notice: buildStatusNotice({
        tone: 'error',
        title: '活动服务暂时不可用',
        message: '未能从后端获取真实活动数据，请稍后重试或检查服务状态。',
      }),
    };
  }

  if (!activities.length || !hasUpcomingActivities(activities, now)) {
    if (allowDemoFallback) {
      return {
        activities: sortActivities(mockActivities),
        notice: buildStatusNotice({
          tone: 'demo',
          title: '当前使用演示数据',
          message: '由于接口限制或网络原因，先用演示数据继续打磨预览体验。',
        }),
      };
    }

    notice = buildStatusNotice({
      tone: 'warning',
      title: !activities.length ? '当前暂无真实活动数据' : '当前暂无未来活动',
      message: !activities.length
        ? '后端已连接，但当前没有可展示的真实活动数据。'
        : '后端已返回真实活动，但未来活动不足，建议继续补来源或等待同步。',
      meta: sourceSummary,
    });
  }

  return { activities, notice };
}
