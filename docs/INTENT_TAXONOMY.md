# Intent Taxonomy

## 1. Purpose

The intent classifier predicts the primary operation requested in a natural-language instruction. It does not predict the exact Bash utility or command syntax.

NL2Bash provides natural-language descriptions paired with Bash commands, but it does not provide intent-classification labels. The labels below are project annotations, not labels copied from the source dataset.

## 2. Primary intent labels

| Label | Definition | Typical command utilities |
|---|---|---|
| `file_discovery` | Locate or list files and directories using names, paths, types, sizes, or timestamps. | `find`, `ls`, `file`, `which`, `basename`, `dirname` |
| `text_search_processing` | Search, inspect, filter, count, compare, sort, join, or transform text and file contents. | `grep`, `awk`, `sed`, `cut`, `sort`, `uniq`, `wc`, `head`, `tail`, `tr` |
| `file_directory_management` | Create, copy, move, rename, remove, link, or otherwise change files and directories. | `cp`, `mv`, `rm`, `mkdir`, `rmdir`, `ln`, `touch` |
| `permissions_ownership` | Read or change access permissions, ownership, or group ownership. | `chmod`, `chown`, `chgrp` |
| `process_job_management` | Inspect, signal, start, stop, or manage processes and shell jobs. | `ps`, `top`, `kill`, `pstree`, `jobs`, `bg`, `fg` |
| `system_information` | Inspect operating-system, host, user, storage, filesystem, date, or resource information. | `df`, `du`, `uname`, `hostname`, `whoami`, `mount`, `date` |
| `network_remote_operations` | Inspect network connectivity or configuration, resolve names, connect to remote systems, or transfer data remotely. | `ping`, `dig`, `ifconfig`, `ssh`, `scp`, `rsync`, `curl`, `wget` |
| `archive_compression` | Create, inspect, extract, compress, or decompress archives and compressed files. | `tar`, `gzip`, `gunzip`, `bzip2`, `zcat`, `cpio` |
| `shell_environment_session` | Inspect or change the current shell session, working directory, environment, history, or shell options. | `cd`, `pwd`, `env`, `history`, `shopt`, `source`, `alias` |
| `other_or_ambiguous` | The request is outside the initial supported scope, has no clear primary operation, or cannot be assigned confidently. | Not tied to a fixed utility list. |

Utility examples are indicative only. A utility may participate in requests from different intent categories.

## 3. Annotation rules

1. Label the user's requested outcome, not the first utility that appears in the generated command.
2. Assign one primary intent per request.
3. For a pipeline, consider the whole requested outcome. Do not label each utility separately.
4. Use `file_discovery` when the goal is to locate paths based on names, paths, types, sizes, or timestamps. Use `text_search_processing` when the goal is to find, count, compare, sort, or transform file contents. If the selection condition is owner, group, or permission bits (readable, writable, executable, SUID, or sticky), use `permissions_ownership`, even when the command uses `find`.
5. Use `permissions_ownership` when changing access or ownership is the main requested outcome, even if the command also traverses directories.
6. Use `network_remote_operations` for remote access, connectivity, name resolution, and remote transfer. Local file copying belongs to `file_directory_management`.
7. Use `archive_compression` when creating or extracting an archive is the main outcome, even if file discovery is part of the command.
8. Use `shell_environment_session` for changes or queries about the current shell state, including the current working directory, shell variables, aliases, history, and shell options.
9. Use `process_job_management` when starting, monitoring, signalling, stopping, or backgrounding a process, including launching an application.
10. Use `network_remote_operations` for SSH authentication/configuration that directly supports remote access, as well as connectivity, name resolution, remote connections, and remote transfers.
11. `system_information` covers inspection of system, host, storage, filesystem, date, and resource information. Requests that change system configuration without fitting another category (for example, changing mount propagation or remounting read-only) use `other_or_ambiguous`.
12. Use `other_or_ambiguous` when two independent operations are equally central, the request is unclear, or the requested operation is outside the supported set. This includes unsupported email, database administration/import, package installation, cron scheduling, arbitrary script execution, media conversion, and file chunking operations unless one supported primary outcome clearly dominates. Do not force an uncertain request into a convenient class.

## 4. Boundary examples

| Request | Label | Reason |
|---|---|---|
| Find all Python files modified yesterday. | `file_discovery` | Locates files by type and modification time. |
| Find Python files containing the word TODO. | `text_search_processing` | The main condition is a match in file contents. |
| Count the number of non-empty lines in a log file. | `text_search_processing` | Measures and filters file content. |
| Move all PDF files into an archive directory. | `file_directory_management` | The requested result is moving files. |
| Make every shell script executable by its owner. | `permissions_ownership` | Changes file permissions. |
| Show processes listening on a port and terminate one. | `process_job_management` | The main operation is process inspection/control. |
| Copy a directory to a remote host over SSH. | `network_remote_operations` | Remote transfer is the requested outcome. |
| Compress all log files into one archive. | `archive_compression` | Creates an archive. |
| Show the current working directory or its base name. | `shell_environment_session` | Queries current shell directory state. |
| Find files owned by a user or writable by others. | `permissions_ownership` | The selection criterion is ownership or access bits, not merely a path property. |
| Print a calendar for a date. | `system_information` | Inspects date/calendar information. |
| Start an application in the background. | `process_job_management` | Starts and manages a process. |
| Copy a file into a local container filesystem. | `file_directory_management` | Changes a local filesystem entry; remote-host transfers are `network_remote_operations`. |
| Find large files and email a report to a team. | `other_or_ambiguous` | Combines separate operations and exceeds the initial scope. |
| Import a compressed SQL dump into a database. | `other_or_ambiguous` | The primary outcome is database import, which is outside the supported taxonomy. |
| Change mount propagation or remount a filesystem read-only. | `other_or_ambiguous` | Changes system configuration rather than inspecting system information. |

## 5. Annotation and quality plan

- Use the natural-language description as the classifier input and the primary basis for its label.
- Use the paired Bash command only as supporting context when a description is genuinely underspecified. If the intended operation remains unclear, use `other_or_ambiguous`.
- Create a manually reviewed, approximately balanced labelled subset. Begin with a pilot of about 50 examples per label (approximately 500 examples) to check whether the definitions are usable.
- Review disagreements and revise the guidance before expanding the annotation set.
- Keep training, development, and test examples in separate data partitions. Do not use test examples for training, prompt tuning, or taxonomy changes.
- Re-review a sample of annotations after the pilot and record any label changes.

The initial pilot size is a planning target, not a claim that these labels or examples already exist.
