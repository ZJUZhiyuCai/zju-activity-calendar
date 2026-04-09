import test from 'node:test';
import assert from 'node:assert/strict';

import {
  getInitialSelectedDate,
  resolveActivityFeedState,
} from '../src/lib/activityState.js';

const mockActivities = [
  {
    id: 'mock-1',
    title: '演示活动',
    activity_date: '2026-04-11',
    activity_time: '19:00',
  },
];

test('returns real activities and warning notice for partial source failures', () => {
  const result = resolveActivityFeedState({
    payload: {
      list: [
        { id: 'a1', title: '真实活动', activity_date: '2026-04-10', activity_time: '14:00' },
      ],
      freshness: 'partial',
      source_status: {
        total_sources: 4,
        ok_sources: 3,
        error_sources: 1,
        generated_at: '2026-04-09T12:00:00Z',
        last_success_sync_at: '2026-04-09T11:00:00Z',
      },
    },
    status: 'fulfilled',
    allowDemoFallback: false,
    mockActivities,
  });

  assert.equal(result.activities[0].id, 'a1');
  assert.equal(result.notice.tone, 'warning');
  assert.match(result.notice.message, /成功 3 个，失败 1 个/);
});

test('returns hard error state when backend request fails and demo fallback is disabled', () => {
  const result = resolveActivityFeedState({
    payload: null,
    status: 'rejected',
    allowDemoFallback: false,
    mockActivities,
  });

  assert.deepEqual(result.activities, []);
  assert.equal(result.notice.tone, 'error');
  assert.match(result.notice.title, /暂时不可用/);
});

test('returns no-upcoming warning instead of mock data when real data has no future activities', () => {
  const result = resolveActivityFeedState({
    payload: {
      list: [
        { id: 'past-1', title: '历史活动', activity_date: '2026-04-01', activity_time: '14:00' },
      ],
      freshness: 'fresh',
      source_status: {
        total_sources: 1,
        ok_sources: 1,
        error_sources: 0,
      },
    },
    status: 'fulfilled',
    allowDemoFallback: false,
    mockActivities,
    now: { format: () => '2026-04-09' },
  });

  assert.equal(result.activities[0].id, 'past-1');
  assert.equal(result.notice.tone, 'warning');
  assert.match(result.notice.title, /暂无未来活动/);
});

test('prefers the next upcoming date for initial selection', () => {
  const selectedDate = getInitialSelectedDate(
    [
      { id: 'past', activity_date: '2026-04-01', activity_time: '14:00' },
      { id: 'next', activity_date: '2026-04-10', activity_time: '10:00' },
      { id: 'later', activity_date: '2026-04-11', activity_time: '09:00' },
    ],
    { format: () => '2026-04-09' },
  );

  assert.equal(selectedDate, '2026-04-10');
});
