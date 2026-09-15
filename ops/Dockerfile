FROM postgres:17-alpine
RUN apk add --no-cache age bash
COPY backup.sh restore.sh test_backup_restore.sh /usr/local/bin/
RUN chmod 0555 /usr/local/bin/backup.sh /usr/local/bin/restore.sh /usr/local/bin/test_backup_restore.sh
ENTRYPOINT ["/bin/bash"]
