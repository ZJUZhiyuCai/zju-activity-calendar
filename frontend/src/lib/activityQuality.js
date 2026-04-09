const COMPLETENESS_COPY = {
  complete: {
    label: '信息完整',
    summary: '时间、地点和关键信息基本齐全，可以直接决策是否参加。',
  },
  partial: {
    label: '信息一般',
    summary: '已有部分关键字段，但仍建议点开原文再确认。',
  },
  limited: {
    label: '信息较少',
    summary: '当前仅有标题级或摘要级线索，建议强依赖原文。',
  },
};

const CONFIDENCE_COPY = {
  high: {
    label: '高置信',
    summary: '来源稳定且字段较完整，误判概率相对较低。',
  },
  medium: {
    label: '中置信',
    summary: '来源可信，但仍可能存在字段抽取不完整或语义误差。',
  },
  low: {
    label: '低置信',
    summary: '当前更适合把它当作活动线索，不适合直接下结论。',
  },
};

export function describeActivityCompleteness(activity) {
  const level = activity?.info_completeness_level || 'limited';
  const meta = COMPLETENESS_COPY[level] || COMPLETENESS_COPY.limited;
  return {
    level,
    label: meta.label,
    summary: meta.summary,
    score: activity?.info_completeness_score ?? 0,
    missingFields: Array.isArray(activity?.info_missing_fields) ? activity.info_missing_fields : [],
  };
}

export function describeActivityConfidence(activity) {
  const level = activity?.source_confidence_level || 'low';
  const meta = CONFIDENCE_COPY[level] || CONFIDENCE_COPY.low;
  return {
    level,
    label: meta.label,
    summary: meta.summary,
    score: activity?.source_confidence_score ?? 0,
    reasons: Array.isArray(activity?.source_confidence_reasons) ? activity.source_confidence_reasons : [],
  };
}
