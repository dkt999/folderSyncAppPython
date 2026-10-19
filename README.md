# FolderSync (Python/Qt)

Bản port Python + QtFluentWidgets của **FolderSyncApp** (C# WinForms) sang Ubuntu.

Công cụ đồng bộ thư mục một chiều (đặc biệt từ **ổ đĩa mạng** về máy local)
theo lịch giờ đã cài đặt, có thể tự khởi động cùng hệ thống.

## Tính năng

- **Đồng bộ thủ công**: chọn nguồn/đích, bấm Bắt đầu, xem log + tiến độ trực tiếp.
- **Task hẹn giờ**: danh sách task, mỗi task có nhiều giờ chạy mỗi ngày
  (định dạng `HH:mm`), bật/tắt từng task, nút Chạy ngay / Hủy task.
- **Scheduler**: kiểm tra mỗi 20 giây, đến giờ hẹn tự chạy nền
  (chạy bù trong 2 phút nếu máy vừa mở lên trễ giờ).
- **Mirror**: tùy chọn xóa file thừa ở thư mục đích.
- **Tự khởi động**: bật trong trang Cài đặt (ghi file XDG autostart).
- **Thu nhỏ xuống khay**: bấm X thì ẩn xuống tray, vẫn chạy nền.

## Yêu cầu

- Ubuntu 22.04+ (hoặc distro Linux khác), Python 3.10+
- `rsync` (engine đồng bộ, thay cho `robocopy.exe` bên Windows)
- `cifs-utils` (để mount ổ đĩa mạng SMB, trang "Ổ đĩa mạng" sẽ tự kiểm tra)

## Cài đặt nhanh

```bash
cd foldersync-py
./install.sh            # cài app + tạo shortcut menu
./install.sh --autostart  # cài app + bật tự khởi động cùng hệ thống
```

Hoặc cài tay:

```bash
sudo apt install rsync python3-venv
python3 -m venv venv && venv/bin/pip install -r requirements.txt
venv/bin/python main.py
```

File task lưu tại `~/.config/FolderSyncApp/tasks.json`.

## Trang "Ổ đĩa mạng" — mount SMB/CIFS an toàn

App đọc **đường dẫn thư mục**, nên ổ đĩa mạng cần được mount trước.
Thay vì sửa `/etc/fstab` bằng tay (gõ sai là mệt), dùng trang **Ổ đĩa mạng**
trong app, quy trình 2 bước an toàn:

1. **Mount thử**: app mount share vào thư mục tạm, đọc thử danh sách file.
   Bước này **không đụng gì đến fstab** — sai user/pass hay sai địa chỉ
   thì chỉ báo lỗi, không để lại hậu quả gì.
   Ô Share chấp nhận dán nguyên `smb://server/share/` copy từ Files,
   app tự chuyển sang dạng `//server/share`.
   Share có dấu cách (VD: `//com0068/02. share`) cũng OK —
   app tự escape thành `\040` khi ghi fstab (fstab không chịu được
   dấu cách thô, ghi thẳng là vỡ dòng).
   Trước khi mount, app kiểm tra tên máy có phân giải được qua DNS không;
   nếu không sẽ báo lỗi ngay kèm gợi ý dùng IP (Files tự dò máy trong mạng
   nên mở được `smb://tên-máy/...`, nhưng mount hệ thống thì cần IP hoặc
   tên phân giải được). Mọi bước đều hiện log chi tiết để biết kẹt ở đâu.
2. **Lưu vào fstab & mount**: chỉ mở khóa sau khi mount thử thành công
   (đổi thông tin là phải thử lại). Khi lưu app sẽ:
   - backup `/etc/fstab` thành `/etc/fstab.bak.<ngày-giờ>`,
   - kiểm tra chặt chẽ dòng mới trước khi ghi,
   - ghi xong đọc lại đối chiếu (đúng +1 entry mới coi là xong,
     sai là tự khôi phục bản backup ngay),
   - mật khẩu lưu riêng ở file quyền `600` (`/etc/samba/credentials/`),
     **không** nằm trong fstab.

Mọi thao tác cần quyền root đều đi qua `pkexec` (hiện hộp thoại nhập
mật khẩu của hệ thống), không cần chạy app bằng sudo.

### Ổ mạng lỗi thì máy có khởi động được không?

**Có.** Mọi entry do app tạo ra đều có 2 tùy chọn:

- `nofail` — ổ mạng lỗi/không tới được thì **bỏ qua**, máy boot tiếp bình thường.
  (Không có `nofail`, systemd sẽ chờ hết timeout rồi có thể rớt vào emergency shell.)
- `_netdev` — báo cho systemd biết đây là ổ mạng, chỉ mount sau khi có mạng.

Nút **Kiểm tra fstab** quét nhanh cú pháp `/etc/fstab` bất cứ lúc nào.

Cách thủ công (không dùng app): mở Files → gõ `smb://server/share`,
thư mục sẽ nằm ở `/run/user/$UID/gvfs/...` — nhưng cách này mất sau khi
đăng xuất, không ổn định bằng fstab.

## Bảng tương đương robocopy → rsync

| robocopy (Windows) | rsync (bản này) |
|---|---|
| `/E` (đệ quy) | `-r` |
| copy timestamp | `-t` + `--modify-window=2` (ngưỡng 2s giống robocopy) |
| `/Z` (restartable) | `--partial` |
| `/R:3 /W:5` | thử lại cả lần chạy 3 lần, cách nhau 5s |
| `/PURGE` (mirror) | `--delete` |
| exit code 0–7 = thành công | exit code 0 = thành công |
| đếm % theo file | đếm trước số file cần copy (size/mtime), đếm dòng `>` của rsync |

## Cấu trúc

```
main.py                  điểm vào app (--minimized: khởi động ẩn xuống tray)
foldersync/
  models.py              BackupTask (port Models.cs)
  store.py               lưu/đọc tasks.json (port TaskStore.cs)
  sync_engine.py         RsyncRunner: bọc rsync, tiến độ, hủy, thử lại (port RobocopyRunner.cs)
  scheduler.py           QtScheduler: timer 20s + chạy task nền (port BackupScheduler.cs)
  worker.py              SyncWorker: chạy sync trên thread, phát signal
  autostart.py           bật/tắt tự khởi động qua ~/.config/autostart (port Registry Run)
  mounts.py              logic mount SMB/CIFS (validate, build entry, parse fstab)
  privileged.py          thao tác root qua pkexec: mount thử, ghi fstab (backup+đối chiếu),
                         file credentials 600; giao tiếp JSON (chạy: python3 -m foldersync.privileged --help)
  ui/
    main_window.py       cửa sổ chính + tray icon (port MainForm)
    manual_page.py       trang đồng bộ thủ công
    tasks_page.py        trang danh sách task
    task_edit_dialog.py  dialog thêm/sửa task (port TaskEditForm)
    mounts_page.py       trang quản lý ổ đĩa mạng (mount thử → lưu fstab an toàn)
    settings_page.py     trang cài đặt
tests/                   pytest: engine, store, logic scheduler, smoke test GUI offscreen
install.sh               cài đặt trên Ubuntu
```

Chạy test: `python3 -m pytest tests/ -q`
(GUI test cần `QT_QPA_PLATFORM=offscreen` nếu máy không có màn hình.)
