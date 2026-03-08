import curses
from rc import Movement

bot = Movement()

def main(stdscr):
    stdscr.nodelay(True)
    stdscr.timeout(50)
    stdscr.clear()
    stdscr.addstr(0, 0, "WASD to move | SPACE to stop | ESC to quit")

    drive = "stopped"
    steer = "straight"

    while True:
        key = stdscr.getch()
        if key == -1:
            continue
        if key == 27:
            bot.cleanup()
            return

        if key == ord('w'):
            drive = "forward"
            bot.forward()
        elif key == ord('a'):
            steer = "left"
            bot.left()
        elif key == ord('d'):
            steer = "right"
            bot.right()
        elif key == ord('s'):
            steer = "straight"
            bot.straight()
        elif key == ord(' '):
            drive = "stopped"
            bot.stop()

        stdscr.addstr(2, 0, f"Drive: {drive}      ")
        stdscr.addstr(3, 0, f"Steer: {steer}      ")
        stdscr.refresh()

curses.wrapper(main)
