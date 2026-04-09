## Summary

- What changed?
- Why is this needed?

## Validation

- [ ] `python3 -m unittest discover -s we-mp-rss/tests`
- [ ] `cd frontend && npm run test:smoke`
- [ ] `cd frontend && npm run build`
- [ ] I verified docs/config changes if this PR changes runtime behavior

## Risk

- User-facing risk:
- Deployment/config risk:
- Rollback plan:

## Checklist

- [ ] I updated docs if behavior or deployment steps changed
- [ ] I called out any known gaps or follow-up work
- [ ] I did not reintroduce production mock fallback or implicit startup side effects
