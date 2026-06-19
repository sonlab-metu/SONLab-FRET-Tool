# Wiki source

This folder holds the source Markdown for the project's **GitHub Wiki**. It is kept under version control here so the wiki can be reviewed in pull requests and edited offline. Each `.md` file becomes one wiki page; `[[Page Name]]` links resolve between pages.

## Pages

| File | Wiki page |
|------|-----------|
| `Home.md` | Home (landing page) |
| `_Sidebar.md` | Navigation sidebar (shown on every page) |
| `_Footer.md` | Footer (shown on every page) |
| `Installation.md` | Installation |
| `User-Interface-Overview.md` | User Interface Overview |
| `Segmentation.md` | Cellpose & Manual Segmentation |
| `Bleed-Through-Correction.md` | Bleed-Through Correction |
| `FRET-Analysis.md` | FRET Analysis |
| `Results-and-Visualization.md` | Results and Visualization |
| `Workflows-and-Data-Flow.md` | Workflows and Data Flow |
| `File-Formats.md` | File Formats |
| `Troubleshooting-and-FAQ.md` | Troubleshooting and FAQ |

## Images

All figures live in `images/` and are embedded in the pages. PNG screenshots use Markdown image syntax; the three portrait `*-pipeline.svg` flow diagrams use a width-constrained HTML `<img>` tag. See `images/README.md` for the full inventory and where each file is used.

## Publishing to the GitHub Wiki

The wiki is a separate Git repository (`<repo>.wiki.git`). It must be initialized once: enable the Wiki feature in the repository settings and create any first page in the web UI. After that, publish with the helper script:

```bash
./publish_to_github_wiki.sh
# or target a specific repo's wiki:
WIKI_REMOTE=git@github.com:<owner>/<repo>.wiki.git ./publish_to_github_wiki.sh
```

The script clones the wiki repo, copies the pages (excluding this `README.md`) and the `images/` folder, then commits and pushes. To do it by hand instead:

```bash
git clone git@github.com:<owner>/<repo>.wiki.git
cp wiki/*.md <repo>.wiki/            # excluding README.md
cp -r wiki/images <repo>.wiki/
cd <repo>.wiki && git add . && git commit -m "Update user guide" && git push
```

GitHub renders `_Sidebar.md` and `_Footer.md` automatically on every page. The repo-side `README.md` files are documentation and are not published as wiki pages.
