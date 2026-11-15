# Raw data manifest

Bulky per-event outputs (`*-reports.csv`, `*-decisions.csv`, `*-hops.csv`, `*-workload.csv`) and MATLAB random-stream
dumps (`*.bin`, outside `matlab_reference/`) are not stored in Git. They are attached, compressed with xz, to the
GitHub Release **v1.0.0** of this repository. Every summary, per-round CSV, metrics file, `.sca` file, log and figure
is in Git. Paths inside the archives are relative to the repository root; extract with `tar -xJf <archive>` there.
The full file list of each archive is in `docs/raw_data_lists/`.

| archive | files | raw size | compressed | SHA-256 |
|---|---|---|---|---|
| `raw_archive.tar.xz` | 167 | 619 MB | 74.5 MB | `e68e0e18d4bba2cf9c4880a33a2fb8474aaaba5c294c2f7799ce1223fd9cf627` |
| `raw_matlab_validation_v2-v11.tar.xz` | 447 | 651 MB | 99.0 MB | `f250a43e988b6f497a53f7a06206c5b6ea99bd4f005d04b3b94b6c4fd91711ec` |
| `raw_misc_checks_logs_placement.tar.xz` | 88 | 148 MB | 27.1 MB | `c8cad14b19b8eb8cdd4075635f225b3428b6b9893b5a864d507b04fc43d3006e` |
| `raw_results.tar.xz` | 92 | 163 MB | 31.7 MB | `f69bec4a0c6d7fcf5b33928e305a8a4dc06f6a2ad52dd2a4d1981fb4bec4b7fc` |
| `raw_results_200node_optimization.tar.xz` | 264 | 2,398 MB | 116.3 MB | `71840f9fa2918186e2f2acf0663ab6bdaed0242fdef8df2904fa5ece7b885442` |
| `raw_results_controlled.tar.xz` | 80 | 204 MB | 40.1 MB | `329b58d1974a92f86d7ccc8114fe5daff08ae6cce27cec29d31904ce8cd16922` |
| `raw_results_environmental.tar.xz` | 50 | 401 MB | 32.9 MB | `baf07811b92855a2e4f4d50d2d9f530249b094d39d735ae615b52ee8ff22b137` |
| `raw_results_environmental_500.tar.xz` | 60 | 1,138 MB | 92.2 MB | `25bb95c2b1c9b0f548aa36f107161d7babfcc603322540f56329544b84d21e52` |
| `raw_results_multi_scenario.tar.xz` | 178 | 1,511 MB | 179.1 MB | `d7815a22a9e193ed189d81041560fd8b4c0b37fdc1a1ad185558629cc6a9865b` |
| `raw_results_research_upgrade.tar.xz` | 41 | 152 MB | 21.9 MB | `54ee17b422caa65bccfd4d7ab1d52ef7b960966b69e7be82f8df008d6e295660` |
| `raw_results_v2_10node_all.tar.xz` | 164 | 81 MB | 11.2 MB | `e2ecfec4f5146ef62ff9bfeec2804691c87bac6c49ef4399db1ba87f8d339786` |
| `raw_results_v2_scaling_all.tar.xz` | 92 | 463 MB | 100.5 MB | `92b90019342234a08a16065a8b078fc4cb47f93d5df358f7643f13cf595472a3` |
