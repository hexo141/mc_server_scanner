print("Loading mc_server_scanner.py...")
import socket
import threading
import sys
import time
import mcstatus
import keyboard
import re
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn, SpinnerColumn
from rich.style import Style
from rich.text import Text
from rich.live import Live
from rich.layout import Layout
import os
print("Imports loaded.")
print("--- Starting mc_server_scanner.py ---")
# 初始化控制台和样式配置 - 终端风格
console = Console()
TITLE_STYLE = Style(color="cyan", bold=True)
MENU_ITEM_STYLE = Style(color="white")
SELECTED_STYLE = Style(color="green", bold=True)
INFO_STYLE = Style(color="blue")
SUCCESS_STYLE = Style(color="green")
WARNING_STYLE = Style(color="yellow")
ERROR_STYLE = Style(color="red")
BORDER_STYLE = "green"
PANEL_WIDTH = 80

# 配置参数
DEFAULT_PORT = 25565
DEFAULT_THREAD_NUM = 50
MIN_THREAD = 1
MAX_THREAD = 200
FAST_TIMEOUT = 0.2
SLOW_TIMEOUT = 1.0
found_servers = []
found_lock = threading.Lock()
pause_flag = threading.Event()
pause_flag.set()

# 线程安全的计数器
current_target = 0
counter_lock = threading.Lock()
latest_scanned = "等待启动..."
mc_scan_mode = False

def clear_input_buffer():
    """清空键盘输入缓冲区"""
    try:
        # Windows系统
        import msvcrt
        while msvcrt.kbhit():
            msvcrt.getch()
    except:
        # Unix/Linux系统
        try:
            import termios
            termios.tcflush(sys.stdin, termios.TCIOFLUSH)
        except:
            pass

def get_port_type(ip, port):
    """获取端口类型"""
    try:
        # 检查TCP
        tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_sock.settimeout(1)
        tcp_result = tcp_sock.connect_ex((ip, port))
        tcp_sock.close()
        
        if tcp_result == 0:
            return "TCP"
        else:
            return "Closed"
    except:
        return "Unknown"

def print_header():
    """打印程序标题"""
    os.system('cls' if os.name == 'nt' else 'clear')
    console.print("\n" + "=" * PANEL_WIDTH, style=TITLE_STYLE)
    title = Text(" MC服务器/端口扫描器 ", style=TITLE_STYLE, justify="center")
    console.print(title)
    console.print("=" * PANEL_WIDTH + "\n", style=TITLE_STYLE)

def ip_to_int(ip):
    """IP地址转整数"""
    parts = list(map(int, ip.split('.')))
    return (parts[0] << 24) + (parts[1] << 16) + (parts[2] << 8) + parts[3]

def int_to_ip(num):
    """整数转IP地址"""
    return f"{(num >> 24) & 255}.{(num >> 16) & 255}.{(num >> 8) & 255}.{num & 255}"

def get_mc_server_info(ip, port):
    """获取Minecraft服务器信息"""
    try:
        start_time = time.time()
        server = mcstatus.JavaServer.lookup(f"{ip}:{port}", timeout=2)
        status = server.status()
        latency = int((time.time() - start_time) * 1000)  # 计算延迟(毫秒)
        return {
            "is_mc": True,
            "version": status.version.name,
            "players": f"{status.players.online}/{status.players.max}",
            "latency": latency,
            "motd": status.description,
            "plugins": getattr(status, 'plugins', []),
            "mods": getattr(status, 'mods', []),
            "favicon": getattr(status, 'favicon', None)
        }
    except:
        try:
            start_time = time.time()
            server = mcstatus.BedrockServer.lookup(f"{ip}:{port}", timeout=2)
            status = server.status()
            latency = int((time.time() - start_time) * 1000)  # 计算延迟(毫秒)
            return {
                "is_mc": True,
                "version": f"Bedrock {status.version.version}",
                "players": f"{status.players.online}/{status.players.max}",
                "latency": latency,
                "motd": status.motd,
                "map": getattr(status, 'map', '未知'),
                "gamemode": getattr(status, 'gamemode', '未知')
            }
        except:
            # 测试TCP连接延迟
            try:
                start_time = time.time()
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(2)
                s.connect((ip, port))
                latency = int((time.time() - start_time) * 1000)
                s.close()
            except:
                latency = "超时"
                
            return {
                "is_mc": False,
                "version": "未知",
                "players": "未知",
                "latency": latency
            }

def scan_ip_port(ip, port, progress, task_id, is_slow=False):
    """扫描单个IP的指定端口"""
    global latest_scanned
    timeout = SLOW_TIMEOUT if is_slow else FAST_TIMEOUT
    try:
        with counter_lock:
            latest_scanned = f"{ip}:{port}"

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        start_time = time.time()
        result = s.connect_ex((ip, port))
        latency = int((time.time() - start_time) * 1000)  # 计算延迟(毫秒)
        
        if result == 0:
            mc_info = {
                "is_mc": False,
                "version": "未知",
                "players": "未知",
                "latency": latency
            }
            
            if mc_scan_mode:
                mc_info = get_mc_server_info(ip, port)
            
            with found_lock:
                if not any(server[0] == ip and server[1] == port for server in found_servers):
                    found_servers.append((ip, port, mc_info["is_mc"], mc_info["version"], mc_info["players"], mc_info["latency"]))
                    
                    if mc_info["is_mc"]:
                        console.print(f"[green]✓ 发现服务器: [white]{ip}:{port}[/white] | {latency}ms | {get_port_type(ip,port)} |版本: [cyan]{mc_info['version']}[/cyan] | 玩家: [yellow]{mc_info['players']}[/yellow][/green]")
                    else:
                        console.print(f"[yellow]! 发现开放端口: [white]{ip}:{port}[/white] | {latency}ms | {get_port_type(ip,port)}[/yellow]")
        
        s.close()
    except socket.timeout:
        if not is_slow:
            scan_ip_port(ip, port, progress, task_id, is_slow=True)
    except Exception:
        pass
    finally:
        progress.update(task_id, advance=1, current_target=latest_scanned)

def scan_range_worker(start_int, end_int, port, progress, task_id):
    """IP范围扫描工作线程"""
    global current_target
    while True:
        pause_flag.wait()
        with counter_lock:
            if current_target > (end_int - start_int):
                break
            ip_num = start_int + current_target
            current_target += 1
        ip = int_to_ip(ip_num)
        scan_ip_port(ip, port, progress, task_id)

def scan_single_ip_worker(ip, start_port, end_port, progress, task_id):
    """单个IP的端口范围扫描工作线程"""
    global current_target
    total_ports = end_port - start_port + 1
    while True:
        pause_flag.wait()
        with counter_lock:
            if current_target >= total_ports:
                break
            port = start_port + current_target
            current_target += 1
        scan_ip_port(ip, port, progress, task_id)

def get_valid_input(prompt_text, input_type=str, validation=None):
    """获取并验证用户输入"""
    prompt = Text(prompt_text, style=INFO_STYLE)
    while True:
        try:
            user_input = input(prompt).strip()
            if not user_input:
                if input_type == int:
                    return None
                else:
                    console.print("输入不能为空，请重新输入", style=ERROR_STYLE)
                    continue
                    
            value = input_type(user_input)
            if validation and not validation(value):
                console.print("输入无效，请重新输入", style=ERROR_STYLE)
                continue
            return value
        except ValueError:
            console.print(f"请输入有效的{input_type.__name__}", style=ERROR_STYLE)

def validate_ip(ip):
    """验证IP地址格式"""
    parts = ip.split('.')
    if len(parts) != 4:
        return False
    for part in parts:
        if not part.isdigit() or not (0 <= int(part) <= 255):
            return False
    return True

def validate_host(host):
    """验证主机（支持IP地址或域名）"""
    if not host:
        return False
        
    if validate_ip(host):
        return True
    
    if len(host) > 255:
        return False
    if host and host[-1] == '.':
        host = host[:-1]
    allowed = re.compile(r"(?!-)[A-Z\d-]{1,63}(?<!-)$", re.IGNORECASE)
    return all(allowed.match(x) for x in host.split('.'))

def validate_port(port):
    """验证端口范围"""
    return 1 <= port <= 65535

def get_arrow_key_selection(prompt, options):
    """修复的方向键选择函数 - 减少闪烁"""
    selected = 0
    last_selected = -1
    clear_input_buffer()
    
    while True:
        # 只有当选择变化时才刷新界面
        if selected != last_selected:
            last_selected = selected
            os.system('cls' if os.name == 'nt' else 'clear')
            print_header()
            
            prompt_text = Text(prompt, justify="center")
            console.print(Panel(
                prompt_text,
                border_style=BORDER_STYLE,
                style=INFO_STYLE,
                width=PANEL_WIDTH,
                expand=False
            ))
            
            console.print("\n请选择：\n")
            
            for i, option in enumerate(options):
                if i == selected:
                    console.print(f"→ {option}", style=SELECTED_STYLE)
                else:
                    console.print(f"  {option}", style=MENU_ITEM_STYLE)
            
            console.print("\n提示：使用↑↓方向键选择，回车键确认")
        
        # 使用阻塞读取，避免CPU占用
        event = keyboard.read_event()
        if event.event_type == keyboard.KEY_DOWN:
            if event.name == 'up':
                selected = (selected - 1) % len(options)
            elif event.name == 'down':
                selected = (selected + 1) % len(options)
            elif event.name == 'enter':
                clear_input_buffer()
                return selected
            elif event.name == 'esc':
                clear_input_buffer()
                return len(options) - 1

def confirm_mc_mode():
    """确认是否开启MC扫描模式"""
    global mc_scan_mode
    choice = get_arrow_key_selection("是否开启MC扫描模式?", ["是", "否"])
    mc_scan_mode = (choice == 0)
    
    # 减少界面刷新，直接显示结果
    console.print("\n")
    if mc_scan_mode:
        console.print("✓ 已开启MC扫描模式", style=SUCCESS_STYLE)
        console.print("   将尝试获取服务器版本和玩家信息", style=INFO_STYLE)
    else:
        console.print("! 未开启MC扫描模式", style=WARNING_STYLE)
        console.print("   仅检测开放端口", style=INFO_STYLE)
    
    time.sleep(1)

def show_menu():
    """显示主菜单 - 减少闪烁"""
    menu_items = [
        "1. IP范围扫描（指定端口）",
        "2. 单个主机端口扫描（支持域名和IP）",
        "3. MC服务器状态检测",
        "4. 退出"
    ]
    
    return get_arrow_key_selection("请选择扫描模式", menu_items) + 1

def ip_range_scan():
    """IP范围扫描模式 - 减少界面刷新"""
    # 合并多个界面刷新
    console.clear()
    print_header()
    console.print(Panel("IP范围扫描模式", border_style=BORDER_STYLE, style=TITLE_STYLE, width=PANEL_WIDTH))
    console.print("\n")
    
    confirm_mc_mode()
    
    # 直接在同一个界面中获取配置
    console.print("\n请输入以下信息（按回车键确认）\n")
    
    start_ip = get_valid_input("请输入起始IP: ", str, validate_ip)
    end_ip = get_valid_input("请输入结束IP: ", str, validate_ip)
    
    port_input = get_valid_input(f"请输入扫描端口（默认{DEFAULT_PORT}）: ", int, validate_port)
    port = port_input if port_input is not None else DEFAULT_PORT
    
    thread_input = get_valid_input(f"请输入线程数（{MIN_THREAD}-{MAX_THREAD}，默认{DEFAULT_THREAD_NUM}）: ", int, lambda x: MIN_THREAD <= x <= MAX_THREAD)
    thread_num = thread_input if thread_input is not None else DEFAULT_THREAD_NUM
    
    try:
        start_int = ip_to_int(start_ip)
        end_int = ip_to_int(end_ip)
    except ValueError:
        console.print("\nIP格式错误", style=ERROR_STYLE)
        input("\n按回车键返回主菜单...")
        return
    
    if start_int > end_int:
        console.print("\n起始IP不能大于结束IP", style=ERROR_STYLE)
        input("\n按回车键返回主菜单...")
        return
        
    total_ips = end_int - start_int + 1
    
    # 显示配置确认
    console.print("\n")
    scan_range_str = f"{start_ip} -> {end_ip}"
    console.print(Panel(
        f"扫描范围: {scan_range_str}\n"
        f"总IP数: {total_ips}\n"
        f"扫描端口: {port}\n"
        f"线程数: {thread_num}\n"
        f"MC扫描模式: {'开启' if mc_scan_mode else '关闭'}",
        title="扫描配置确认",
        border_style="yellow",
        width=PANEL_WIDTH
    ))
    input("\n按回车键开始扫描...")
    
    global current_target, found_servers
    current_target = 0
    found_servers = []
    
    # 开始扫描
    console.clear()
    print_header()
    with Progress(
        SpinnerColumn("dots", style="green"),
        TextColumn("[progress.description]{task.description}", style="white"),
        BarColumn(bar_width=50, style=Style(bgcolor="#222222", color="green")),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%", style="green"),
        TimeRemainingColumn(),
        TextColumn("当前: {task.fields[current_target]}"),
        console=console,
        transient=True
    ) as progress:
        task_id = progress.add_task("正在扫描...", total=total_ips, current_target="准备中...")
        
        threads = []
        for _ in range(thread_num):
            t = threading.Thread(target=scan_range_worker, args=(start_int, end_int, port, progress, task_id))
            t.daemon = True
            t.start()
            threads.append(t)
        
        for t in threads:
            t.join()
    
    show_scan_results()

def single_ip_port_scan():
    """单个主机端口扫描模式 - 减少界面刷新"""
    console.clear()
    print_header()
    console.print(Panel("单个主机端口扫描模式", border_style=BORDER_STYLE, style=TITLE_STYLE, width=PANEL_WIDTH))
    console.print("\n")
    
    confirm_mc_mode()
    
    # 直接在同一个界面中获取配置
    console.print("\n请输入以下信息（按回车键确认）\n")
    
    host = get_valid_input("请输入目标IP或域名: ", str, validate_host)
    
    try:
        ip = socket.gethostbyname(host)
        console.print(f"已解析: {host} -> {ip}", style=INFO_STYLE)
    except socket.gaierror:
        console.print(f"无法解析主机: {host}", style=ERROR_STYLE)
        input("\n按回车键返回主菜单...")
        return
    
    start_port = get_valid_input("请输入起始端口: ", int, validate_port)
    end_port = get_valid_input("请输入结束端口: ", int, validate_port)
    
    if start_port > end_port:
        console.print("\n起始端口不能大于结束端口", style=ERROR_STYLE)
        input("\n按回车键返回主菜单...")
        return
        
    thread_input = get_valid_input(f"请输入线程数（{MIN_THREAD}-{MAX_THREAD}，默认{DEFAULT_THREAD_NUM}）: ", int, lambda x: MIN_THREAD <= x <= MAX_THREAD)
    thread_num = thread_input if thread_input is not None else DEFAULT_THREAD_NUM
    
    total_ports = end_port - start_port + 1
    
    # 显示配置确认
    console.print("\n")
    console.print(Panel(
        f"目标主机: {host}\n"
        f"解析IP: {ip}\n"
        f"端口范围: {start_port} -> {end_port}\n"
        f"总端口数: {total_ports}\n"
        f"线程数: {thread_num}\n"
        f"MC扫描模式: {'开启' if mc_scan_mode else '关闭'}",
        title="扫描配置确认",
        border_style="yellow",
        width=PANEL_WIDTH
    ))
    input("\n按回车键开始扫描...")
    
    global current_target, found_servers
    current_target = 0
    found_servers = []
    
    # 开始扫描
    console.clear()
    print_header()
    with Progress(
        SpinnerColumn("dots", style="green"),
        TextColumn("[progress.description]{task.description}", style="white"),
        BarColumn(bar_width=50, style=Style(bgcolor="#222222", color="green")),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%", style="green"),
        TimeRemainingColumn(),
        TextColumn("当前: {task.fields[current_target]}"),
        console=console,
        transient=True
    ) as progress:
        task_id = progress.add_task("正在扫描...", total=total_ports, current_target="准备中...")
        
        threads = []
        for _ in range(thread_num):
            t = threading.Thread(target=scan_single_ip_worker, args=(ip, start_port, end_port, progress, task_id))
            t.daemon = True
            t.start()
            threads.append(t)
        
        for t in threads:
            t.join()
    
    show_scan_results()

def mc_server_status_check():
    """MC服务器状态检测功能"""
    console.clear()
    print_header()
    console.print(Panel("MC服务器状态检测", border_style=BORDER_STYLE, style=TITLE_STYLE, width=PANEL_WIDTH))
    console.print("\n")
    
    console.print("请输入服务器地址（IP或域名，可包含端口）", style=INFO_STYLE)
    console.print("示例: example.com:25565 或 192.168.1.1 或 mc.example.com", style=INFO_STYLE)
    
    server_input = get_valid_input("服务器地址: ", str, lambda x: len(x) > 0)
    
    # 解析输入，提取主机和端口
    if ":" in server_input:
        parts = server_input.split(":")
        host = parts[0]
        try:
            port = int(parts[1])
            if not validate_port(port):
                console.print("端口号无效，使用默认端口25565", style=WARNING_STYLE)
                port = DEFAULT_PORT
        except (ValueError, IndexError):
            console.print("端口号无效，使用默认端口25565", style=WARNING_STYLE)
            port = DEFAULT_PORT
    else:
        host = server_input
        port = DEFAULT_PORT
    
    # 解析主机名
    try:
        ip = socket.gethostbyname(host)
        console.print(f"已解析: {host} -> {ip}", style=INFO_STYLE)
    except socket.gaierror:
        console.print(f"无法解析主机: {host}", style=ERROR_STYLE)
        input("\n按回车键返回主菜单...")
        return
    
    console.print(f"\n正在检测服务器 {host}:{port} 的状态...", style=INFO_STYLE)
    
    # 获取服务器信息
    with console.status("[bold green]正在查询服务器信息...", spinner="dots") as status:
        server_info = get_mc_server_info(ip, port)
    
    # 显示服务器信息
    console.print("\n")
    console.print(Panel("服务器状态信息", border_style="green", style=SUCCESS_STYLE, width=PANEL_WIDTH))
    
    info_table = Table(show_header=False, box=None, width=PANEL_WIDTH)
    info_table.add_column("属性", style="cyan", width=15)
    info_table.add_column("值", style="white")
    
    info_table.add_row("服务器地址", f"{host}:{port}")
    info_table.add_row("解析IP", ip)
    info_table.add_row("延迟", f"{server_info['latency']}ms")
    info_table.add_row("Minecraft服务器", "是" if server_info["is_mc"] else "否")
    
    if server_info["is_mc"]:
        info_table.add_row("版本", server_info["version"])
        info_table.add_row("在线玩家", server_info["players"])
        
        # 显示MOTD
        motd_text = server_info.get("motd", "未知")
        if isinstance(motd_text, str) and motd_text:
            info_table.add_row("MOTD", motd_text)
        
        # 显示其他信息（如果有）
        if "plugins" in server_info and server_info["plugins"]:
            info_table.add_row("插件", ", ".join(server_info["plugins"]))
        
        if "mods" in server_info and server_info["mods"]:
            info_table.add_row("模组", ", ".join([mod.name for mod in server_info["mods"]]))
        
        if "map" in server_info:
            info_table.add_row("地图", server_info["map"])
        
        if "gamemode" in server_info:
            info_table.add_row("游戏模式", server_info["gamemode"])
    else:
        info_table.add_row("端口状态", "开放" if server_info["latency"] != "超时" else "关闭或无法访问")
    
    console.print(info_table)
    
    input("\n按回车键返回主菜单...")

def show_scan_results():
    """显示扫描结果 - 减少界面刷新"""
    console.clear()
    print_header()
    console.print(Panel("扫描完成！", border_style="green", style=SUCCESS_STYLE, width=PANEL_WIDTH))
    console.print("\n")
    
    if found_servers:
        table = Table(
            title="发现的服务器/端口",
            show_header=True,
            header_style="bold cyan",
            border_style="white",
            title_justify="center",
            width=PANEL_WIDTH
        )
        table.add_column("序号", justify="center", style="yellow", width=6)
        table.add_column("IP地址", justify="center", style="cyan", no_wrap=True)
        table.add_column("端口", justify="center", style="magenta", width=8)
        table.add_column("延迟", justify="center", style="green", width=8)
        table.add_column("类型", justify="center", style="green")
        table.add_column("版本", justify="center", style="blue")
        table.add_column("玩家数", justify="center", style="yellow")
        
        for idx, (ip, port, is_mc, version, players, latency) in enumerate(found_servers, 1):
            server_type = "MC服务器" if is_mc else "普通端口"
            table.add_row(str(idx), ip, str(port), f"{latency}ms", server_type, version, players)
            
        console.print(table)
    else:
        console.print(Panel("未发现开放端口", border_style="yellow", style=WARNING_STYLE, width=PANEL_WIDTH))
    
    input("\n按回车键返回主菜单...")

def main():
    """主函数 - 修复启动和闪烁问题"""
    try:
        # 程序启动时立即清空键盘缓冲区
        clear_input_buffer()
        
        while True:
            choice = show_menu()
            if choice == 1:
                ip_range_scan()
            elif choice == 2:
                single_ip_port_scan()
            elif choice == 3:
                mc_server_status_check()
            elif choice == 4:
                console.clear()
                print_header()
                console.print("感谢使用，再见！", style=SUCCESS_STYLE)
                console.print("\n" + "=" * PANEL_WIDTH + "\n", style=TITLE_STYLE)
                sys.exit(0)
    except KeyboardInterrupt:
        # 处理Ctrl+C，但不退出程序
        console.print("\n\n检测到中断信号，返回主菜单...", style=WARNING_STYLE)
        time.sleep(1)
        main()  # 重新启动主菜单
    except Exception as e:
        console.print(f"\n程序出错: {str(e)}", style=ERROR_STYLE)
        input("\n按回车键返回主菜单...")
        main()

if __name__ == "__main__":
    print("-"* 50)
    print("这个项目会涉及到法律风险，请确保你在合法合规的前提下使用本工具！")
    print("本项目仅供学习交流，请勿用于商业用途！请勿用于攻击等非法用途！请勿用于扫描未经授权的服务器！")
    print("                     Created by hexo141(https://github.com/hexo141)")
    print("-"* 50)
    time.sleep(10)
    print("\033c", end="")
    main()