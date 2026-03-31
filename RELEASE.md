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

**MeasureMe** uses an independent versioning strategy for its monorepo sub-projects.

Tags must be prefixed with the sub-project identifier (e.g. `core-v1.2.0`, `api-v1.2.0` or `fitbit-v1.2.0`).

**NOTE:** Ensure that the relevant code (e.g. `__init__.py`) is committed before preparing the release! 
Wait to create the tag until the changelog is generated and committed.

**NOTE:** When a major (breaking) change affects `core`, ensure you test and update downstream dependents (`fitbitme`, `measureme-web`) if they rely on the breaking changes.

Prepare the release for the changed component(s), as per the instructions.

### Core
For the **core library (`measureme`)**, update the version number in [`init.py`](measureme/src/measureme/__init__.py).

*(Tip: In PowerShell, you can automatically extract the target version safely avoiding quote-escaping problems:)*
```powershell
$code = "import re; match=re.search(r'__version__\s*=\s*[\x22\x27]v?([^\x22\x27]+)[\x22\x27]', open('measureme/src/measureme/__init__.py').read()); print('core-v' + match.group(1)) if match else exit(1)";
$version = python -c $code; if ($LASTEXITCODE -eq 0) { Write-Host "Target Version: $version" } else { Write-Host "Failed to find version" }
```

```powershell
$loc = "measureme"
$comp = "core-v"
$code = "import re; match=re.search(r'__version__\s*=\s*[\x22\x27]v?([^\x22\x27]+)[\x22\x27]', open('measureme/src/measureme/__init__.py').read()); print('$comp' + match.group(1)) if match else exit(1)";
$version = python -c $code; if ($LASTEXITCODE -eq 0) { Write-Host "Target Version: $version" } else { Write-Host "Failed to find version" }
```


### FitBit API
For the **FitBit API project (`fitbitme`)**, update the version number in [`init.py`](fitbitme/src/__init__.py).

```powershell
$loc = "fitbitme"
$comp = "fitbit-v"
$code = "import re; match=re.search(r'__version__\s*=\s*[\x22\x27]v?([^\x22\x27]+)[\x22\x27]', open('fitbitme/src/__init__.py').read()); print('$comp' + match.group(1)) if match else exit(1)";
$version = python -c $code; if ($LASTEXITCODE -eq 0) { Write-Host "Target Version: $version" } else { Write-Host "Failed to find version" }
```

### MeasureMe API
For the **MeasureMe API project (`measureme-web`)**, update the version number in [`init.py`](measureme-web/src/__init__.py).

```powershell
$loc = "measureme-web"
$comp = "api-v"
$code = "import re; match=re.search(r'__version__\s*=\s*[\x22\x27]v?([^\x22\x27]+)[\x22\x27]', open('measureme-web/src/__init__.py').read()); print('$comp' + match.group(1)) if match else exit(1)";
$version = python -c $code; if ($LASTEXITCODE -eq 0) { Write-Host "Target Version: $version" } else { Write-Host "Failed to find version" }
```

## Update the ChangeLog

**MeasureMe** uses an extended version of `auto-changelog` that supports path filtering (`--affects-path`), combined with a custom Jinja2 template (`changelog-template.jinja2`) to automatically strip prefixes like `core-` or `web-` from the markdown headers.

```bash
# 1. Generate the changelog, specifying the new version explicitly so unreleased changes are grouped under it
auto-changelog --tag-prefix $comp --affects-path $loc/ --output $loc/CHANGELOG.md --template changelog-template.jinja2 --latest-version $version

# 2. Add and commit the version bump and the changelog together
git add $loc
git commit -m "Bump version to $version and update changelog"

# 3. Create the tag on this final commit
git tag $version

# 4. Push the branch and the new tag
git push origin development
git push origin $version
```

## Make a GitHub Release

Go to the GitHub project administration page and [publish a release](https://github.com/kev-m/MeasureMe/releases/new) using the newly pushed tag.
Ensure the release notes match the changelog.

Update the `release` branch using a fast-forward merge (safely preserves matching commit hashes):
```bash
git checkout release
git merge --ff-only development
git push origin release
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
