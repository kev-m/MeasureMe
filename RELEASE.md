# Release Procedure
The basic procedure for releasing a new version of **MeasureMe** sub-projects consists of:
- Running the unit tests.
- Checking the documentation
- Create a prefixed tag and update the change log
- Build and Publish the project

## Check the Unit Tests

Run the unit tests from the project top level directory:
```bash
pytest
```

## Create a Prefixed Tag

**MeasureMe** uses a semi-independent versioning strategy for its monorepo sub-projects.

All sub-projects share the same `major.minor` version, but support individual `major.minor.patch`
versions to account for individual improvements.

Tags must be prefixed with the sub-project identifier (e.g. `core-v1.0.0` or `web-v1.2.0`).

### Core
For the **core library (`measureme`)**, update the version number in [`init.py`](measureme\src\measureme\__init__.py).

### FitBit API
For the **FitBit API project (`fitbitme`)**, update the version number in [`init.py`](fitbitme\src\__init__.py).

### MeasureMe API
For the **MeasureMe API project (`measureme-web`)**, update the version number in [`init.py`](fitbitme\src\__init__.py).


**NOTE:** Ensure that the relevant code (e.g. `__init__.py`) is committed before creating the tag!

Create a tag with the current version:
```bash
version=core-v0.0.9
git tag $version
```

*(Tip: In PowerShell, you can automatically extract and tag the core version safely avoiding quote-escaping problems:)*
```powershell
$code = "import re; match=re.search(r'__version__\s*=\s*[\x22\x27]v?([^\x22\x27]+)[\x22\x27]', open('measureme/src/measureme/__init__.py').read()); print('core-v' + match.group(1)) if match else exit(1)";
$version = python -c $code; if ($LASTEXITCODE -eq 0) { git tag $version; Write-Host "Created tag: $version" } else { Write-Host "Failed to find version" }
```

## Update the ChangeLog

**MeasureMe** uses an extended version of `auto-changelog` that supports path filtering (`--affects-path`), combined with a custom Jinja2 template (`changelog-template.jinja2`) to automatically strip prefixes like `core-` or `web-` from the markdown headers.

```bash
# 1. Generate the changelog for a specific sub-project (it will track between the prefixed tags)
auto-changelog --tag-prefix core-v --affects-path measureme/ --output measureme/CHANGELOG.md --template changelog-template.jinja2

# 2. Add and commit the changelog
git add measureme/CHANGELOG.md
git commit -m "Updating CHANGELOG for $version release"

# 3. Move the tag forward to include the changelog commit!
git tag -f $version

# 4. Push the branch and the new tag
git push
git push -f --tags
```

## Make a GitHub Release

Go to the GitHub project administration page and [publish a release](https://github.com/kev-m/MeasureMe/releases/new) using the newly pushed tag.
Ensure the release notes match the changelog.

Update the `release` branch:
```bash
git checkout release
git rebase development
git push -f
git checkout development
```

## Publishing the Package (Manual)

**NOTE:** This project is set up on GitHub for automatic publishing during the GitHub release process (above).
These instructions are for legacy purposes or manual publishing.

The core library (`measureme/`) can be published using `flit` to build and publish the artifact.
(Flit automatically resolves the version dynamically out of `__init__.py` cleanly, ignoring the Git tag prefix).

```bash
cd measureme/
flit build
flit publish
```
