## Git Branching Strategy

We use two branches: `main` holds the production-ready code and `dev` is the
branch on which active development happens.

For development, commit changes on `dev` and push to the remote. Commit messages
must follow [Conventional Commits](https://www.conventionalcommits.org/) syntax,
since semantic release uses them to determine version bumps:

```bash
git checkout dev
# ... work ...
git add -A && git commit
git push origin dev
```

When ready for production, create a PR to merge `dev` into `main`:

```bash
gh pr create --base main --head dev
```