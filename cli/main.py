"""命令行工具主程序"""

import sys
import argparse
from pathlib import Path

# 添加父目录到路径，以便导入email_client
sys.path.insert(0, str(Path(__file__).parent.parent))

from email_client import EmailClient, Config


def cmd_list(args):
    """列出最近邮件"""
    client = EmailClient()
    emails = client.get_recent_emails(days=args.days, limit=args.limit)

    if not emails:
        print(f"最近{args.days}天内没有找到邮件。")
        return

    print(f"📬 最近{args.days}天的邮件列表 (共{len(emails)}封):\n")
    for email in emails:
        print(f"📧 UID: {email.uid}")
        print(f"📅 日期: {email.date.strftime('%Y-%m-%d %H:%M')}")
        print(f"👤 发件人: {email.from_}")
        print(f"📝 主题: {email.subject}")
        print("─" * 50)

    client.disconnect()


def cmd_search(args):
    """搜索邮件"""
    client = EmailClient()
    emails = client.search_emails(subject=args.subject, days=args.days)

    if not emails:
        print(f"未找到主题包含'{args.subject}'的邮件。")
        return

    print(f"📬 搜索结果 (共{len(emails)}封):\n")
    for email in emails:
        print(f"📧 UID: {email.uid}")
        print(f"📅 日期: {email.date.strftime('%Y-%m-%d %H:%M')}")
        print(f"👤 发件人: {email.from_}")
        print(f"📝 主题: {email.subject}")
        print("─" * 50)

    client.disconnect()


def cmd_view(args):
    """查看邮件详情"""
    client = EmailClient()
    email = client.get_email(args.uid)

    if not email:
        print(f"✗ 未找到UID为{args.uid}的邮件")
        return

    print(f"📧 邮件详情 (UID: {email.uid})")
    print("─" * 50)
    print(f"📅 日期: {email.date.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"👤 发件人: {email.from_}")
    print(f"👥 收件人: {email.to}")
    if email.cc:
        print(f"📋 抄送: {email.cc}")
    print(f"📝 主题: {email.subject}")
    print("─" * 50)

    if email.body:
        print(f"📄 文本内容:\n{email.body}")

    if email.attachments:
        print(f"\n📎 附件列表:")
        for i, att in enumerate(email.attachments, 1):
            print(f"  {i}. {att.filename} ({att.size:,} bytes)")

    client.disconnect()


def cmd_download(args):
    """下载附件"""
    client = EmailClient()
    folder = Path(args.folder)

    files = client.download_attachments(args.uid, folder)

    if not files:
        print("✗ 未找到附件或下载失败")
        return

    print(f"✓ 下载完成！共下载{len(files)}个文件")
    print(f"✓ 保存位置: {folder.absolute()}")

    for file_path in files:
        print(f"  • {file_path.name}")

    client.disconnect()


def cmd_batch_download(args):
    """批量下载附件"""
    client = EmailClient()
    folder = Path(args.folder)

    print(f"搜索主题包含'{args.subject}'的邮件...")
    files = client.batch_download_attachments(args.subject, args.days, folder)

    if not files:
        print("✗ 未找到附件或下载失败")
        return

    print(f"✓ 批量下载完成！共下载{len(files)}个文件")
    print(f"✓ 保存位置: {folder.absolute()}")

    for file_path in files:
        print(f"  • {file_path.name}")

    client.disconnect()


def cmd_send(args):
    """发送邮件"""
    client = EmailClient()

    # 处理附件
    attachments = None
    if args.attach:
        attachments = [Path(f) for f in args.attach]

    # 处理抄送
    cc = None
    if args.cc:
        cc = args.cc.split(',')

    # 处理密送
    bcc = None
    if args.bcc:
        bcc = args.bcc.split(',')

    success = client.send_email(
        to=args.to.split(','),
        subject=args.subject,
        body=args.body,
        attachments=attachments,
        cc=cc,
        bcc=bcc
    )

    if success:
        print(f"✓ 邮件发送成功！")
        print(f"  收件人: {args.to}")
        print(f"  主题: {args.subject}")
    else:
        print("✗ 邮件发送失败")

    client.disconnect()


def cmd_reply(args):
    """回复邮件"""
    client = EmailClient()

    # 处理附件
    attachments = None
    if args.attach:
        attachments = [Path(f) for f in args.attach]

    success = client.reply(
        uid=args.uid,
        body=args.body,
        attachments=attachments,
        reply_all=args.reply_all
    )

    if success:
        print(f"✓ 回复发送成功！")
    else:
        print("✗ 回复发送失败")

    client.disconnect()


def cmd_setup(args):
    """配置邮箱"""
    config = Config()

    # 检查是否已经配置
    if config.env_file.exists():
        overwrite = input(f"配置文件{config.env_file}已存在，是否覆盖？(y/N): ")
        if overwrite.lower() != 'y':
            print("操作已取消")
            return

    # 获取配置参数
    email = args.email
    password = args.password
    imap_host = args.imap_host
    imap_port = args.imap_port
    imap_ssl = args.imap_ssl
    smtp_host = args.smtp_host
    smtp_port = args.smtp_port
    smtp_ssl = args.smtp_ssl

    # 如果没有提供参数，则交互式输入
    if not email:
        email = input("请输入邮箱地址: ").strip()

    if not password:
        import getpass
        password = getpass.getpass("请输入邮箱密码或授权码: ").strip()

    if not imap_host:
        imap_host = input("请输入IMAP服务器地址 (默认: mail.cstnet.cn): ").strip()
        imap_host = imap_host or "mail.cstnet.cn"

    if not imap_port:
        imap_port_input = input("请输入IMAP端口 (默认: 993): ").strip()
        imap_port = int(imap_port_input) if imap_port_input else 993

    if imap_ssl is None:
        imap_ssl_input = input("IMAP使用SSL加密? (Y/n): ").strip()
        imap_ssl = imap_ssl_input.lower() not in ('n', 'no', 'false', '0')

    if not smtp_host:
        smtp_host = input("请输入SMTP服务器地址 (默认: mail.cstnet.cn): ").strip()
        smtp_host = smtp_host or "mail.cstnet.cn"

    if not smtp_port:
        smtp_port_input = input("请输入SMTP端口 (默认: 465): ").strip()
        smtp_port = int(smtp_port_input) if smtp_port_input else 465

    if smtp_ssl is None:
        smtp_ssl_input = input("SMTP使用SSL加密? (Y/n): ").strip()
        smtp_ssl = smtp_ssl_input.lower() not in ('n', 'no', 'false', '0')

    # 保存配置
    success = config.save_config(email, password, imap_host, imap_port, imap_ssl, smtp_host, smtp_port, smtp_ssl)

    if success:
        print(f"\n✓ 配置已保存到{config.env_file}")
        print(f"✓ 邮箱: {email}")
        print(f"✓ IMAP: {imap_host}:{imap_port} (SSL: {'是' if imap_ssl else '否'})")
        print(f"✓ SMTP: {smtp_host}:{smtp_port} (SSL: {'是' if smtp_ssl else '否'})")
        print("\n💡 提示: 运行测试命令验证配置:")
        print("  python main.py cli test")
    else:
        print("✗ 配置保存失败")


def cmd_test(args):
    """测试连接"""
    client = EmailClient()
    results = client.test_connection(args.type)

    for key, message in results.items():
        print(message)

    client.disconnect()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='Python邮件客户端 - 命令行工具')
    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # list命令
    parser_list = subparsers.add_parser('list', help='列出最近邮件')
    parser_list.add_argument('--days', type=int, default=3, help='最近几天（默认3）')
    parser_list.add_argument('--limit', type=int, default=20, help='最大数量（默认20）')

    # search命令
    parser_search = subparsers.add_parser('search', help='搜索邮件')
    parser_search.add_argument('--subject', required=True, help='主题关键词')
    parser_search.add_argument('--days', type=int, default=7, help='搜索最近几天（默认7）')

    # view命令
    parser_view = subparsers.add_parser('view', help='查看邮件详情')
    parser_view.add_argument('--uid', required=True, help='邮件UID')

    # download命令
    parser_download = subparsers.add_parser('download', help='下载附件')
    parser_download.add_argument('--uid', required=True, help='邮件UID')
    parser_download.add_argument('--folder', default='downloads', help='下载文件夹（默认downloads）')

    # batch-download命令
    parser_batch = subparsers.add_parser('batch-download', help='批量下载附件')
    parser_batch.add_argument('--subject', required=True, help='主题关键词')
    parser_batch.add_argument('--days', type=int, default=7, help='搜索最近几天（默认7）')
    parser_batch.add_argument('--folder', default='downloads', help='下载文件夹（默认downloads）')

    # send命令
    parser_send = subparsers.add_parser('send', help='发送邮件')
    parser_send.add_argument('--to', required=True, help='收件人（多个用逗号分隔）')
    parser_send.add_argument('--subject', required=True, help='邮件主题')
    parser_send.add_argument('--body', required=True, help='邮件正文')
    parser_send.add_argument('--attach', nargs='*', help='附件文件路径')
    parser_send.add_argument('--cc', help='抄送地址（多个用逗号分隔）')
    parser_send.add_argument('--bcc', help='密送地址（多个用逗号分隔）')

    # reply命令
    parser_reply = subparsers.add_parser('reply', help='回复邮件')
    parser_reply.add_argument('--uid', required=True, help='原邮件UID')
    parser_reply.add_argument('--body', required=True, help='回复正文')
    parser_reply.add_argument('--attach', nargs='*', help='附件文件路径')
    parser_reply.add_argument('--reply-all', action='store_true', help='回复全部')

    # setup命令
    parser_setup = subparsers.add_parser('setup', help='配置邮箱')
    parser_setup.add_argument('--email', help='邮箱地址')
    parser_setup.add_argument('--password', help='邮箱密码或授权码')
    parser_setup.add_argument('--imap-host', help='IMAP服务器地址')
    parser_setup.add_argument('--imap-port', type=int, help='IMAP端口')
    parser_setup.add_argument('--imap-ssl', type=bool, help='IMAP是否使用SSL')
    parser_setup.add_argument('--smtp-host', help='SMTP服务器地址')
    parser_setup.add_argument('--smtp-port', type=int, help='SMTP端口')
    parser_setup.add_argument('--smtp-ssl', type=bool, help='SMTP是否使用SSL')

    # test命令
    parser_test = subparsers.add_parser('test', help='测试连接')
    parser_test.add_argument('--type', choices=['imap', 'smtp', 'both'],
                             default='both', help='测试类型（默认both）')

    # 解析参数
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # 执行对应命令
    command_func = {
        'list': cmd_list,
        'search': cmd_search,
        'view': cmd_view,
        'download': cmd_download,
        'batch-download': cmd_batch_download,
        'send': cmd_send,
        'reply': cmd_reply,
        'setup': cmd_setup,
        'test': cmd_test,
    }.get(args.command)

    if command_func:
        try:
            command_func(args)
        except KeyboardInterrupt:
            print("\n\n操作已取消")
        except Exception as e:
            print(f"✗ 发生错误: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()


if __name__ == '__main__':
    main()
