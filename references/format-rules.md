# rename-papers — filename format rules

Format: `Surname, I. [et al.] (Year) Title - DOI.pdf`

- First author `Surname, Initial.`; append ` et al.` when there is more than one author.
- Year: four-digit publication year in parentheses; missing year → needs review.
- Title: from CrossRef, falling back to PDF-parsed title.
- DOI: appended after ` - `, with `/` replaced by `_`.
- Illegal chars `/ \ : * ? " < > |` → `_`; whitespace collapsed; filename ≤ 200 chars (title truncated to fit).
- Never overwrite; never invent a DOI; only DOIs literally found in the file are used.

Example: `Smith, J. et al. (2023) Deep learning for graphs - 10.1000_xyz123.pdf`
