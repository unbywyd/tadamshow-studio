# Contributing

Thank you for helping. Changes come in as GitHub pull requests.

## How to send a change

1. Fork the repository and make a branch from `main`.
2. Keep the change small and about one thing. Describe what it does and why in the pull request.
3. Run the tests (below) and make sure they pass on your machine. Say which OS you ran them on —
   the kit must work on Windows, macOS and Linux.
4. Never commit secrets (API keys, studio keys, `.env` files), recordings of people, faces or voices,
   or pictures, fonts and music you do not have the rights to.

## Running the tests

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS / Linux: source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Contributor agreement

By sending a contribution (a pull request, a patch, or code in an issue) you agree that:

1. you wrote it yourself, or otherwise have the right to submit it under these terms;
2. you grant the copyright holder of this project (unbywyd) a perpetual, worldwide, non-exclusive,
   royalty-free, irrevocable licence to use, copy, modify, distribute and sublicense your contribution,
   under the project's current licence **and under any other licence, including commercial licences**
   (so the project can keep being offered both free for non-commercial use and under paid commercial terms);
3. you grant the same patent licence for any patent claims of yours that your contribution necessarily
   infringes;
4. you keep the copyright in your contribution and may use it in any other way you like.

If you cannot agree to this (for example, your employer owns your work), please say so in the pull request
before it is merged.
