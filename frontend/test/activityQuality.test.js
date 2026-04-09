import test from 'node:test';
import assert from 'node:assert/strict';

import {
  describeActivityCompleteness,
  describeActivityConfidence,
} from '../src/lib/activityQuality.js';

test('describes complete activities with missing field summary', () => {
  const result = describeActivityCompleteness({
    info_completeness_level: 'complete',
    info_completeness_score: 0.91,
    info_missing_fields: [],
  });

  assert.equal(result.label, '信息完整');
  assert.equal(result.score, 0.91);
  assert.deepEqual(result.missingFields, []);
});

test('describes low-confidence activities with extracted reasons', () => {
  const result = describeActivityConfidence({
    source_confidence_level: 'low',
    source_confidence_score: 0.48,
    source_confidence_reasons: ['公众号文章抽取'],
  });

  assert.equal(result.label, '低置信');
  assert.equal(result.score, 0.48);
  assert.deepEqual(result.reasons, ['公众号文章抽取']);
});
