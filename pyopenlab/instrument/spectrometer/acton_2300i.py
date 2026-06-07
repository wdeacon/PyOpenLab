# pyopenlab code to control Acton spectrometer
# Model SP-2356, see ftp://ftp.princetoninstruments.com/public/manuals/Acton/SP-2300i.pdf
'''Serial driver for the Princeton Instruments Acton SP-2300i monochromator.

This module provides :class:`Acton`, a thin serial wrapper over the SP-2300i
command set covering wavelength moves, grating and turret selection, and
entrance/exit slit and mirror control.

Reference notes from the manual follow.

Monochromator parameters:
    Slits: from 10 micron to 3 mm (width), 4 & 14 mm height
    Detector coverage: ~68.5nm across 1.0inch (25.4mm). (137 nm with 600 g/mm grating)

Software:
    RS-232

Initialization:
    Initialized to wavelength 0.0nm for grating 1
    Will re-initialize on reboot
    Alternative start-up parameters can be programmed (Appendix A)

Commands:
    Single/grouped
    All commands are single words, no spaces
    All commands in string separated by at least one line (\n or \r?)
    Parameters preceed command, separated by at least one space

Port settings:
    9600 baud, 1 stop bit, no parity
    termination character: carriage return (0x0D)

    responds to command when completed with "OK\r\n"
    commands are blocking

Movement commands:
    
    Wavelength commands:
        GOTO/<GOTO> - move to specified wavelength at max speed
        
        NM - blocking move to dest wavelength at user-specified speed
        <NM> - compatibility mode
        >NM - non-blocking, must be terminated with MONO-STOP
            MONO-?DONE - determine if monochromator reached end
            MONO-STOP stops motion
        ?NM - returns current wavelength, units appended
        
        NM/MIN - sets rotation speed
        ?NM/MIN - gets rotation speed
    
    Grating:
        GRATING - place grating in specified wavelength
            assumes correct TURRET
        ?GRATING - return number of gratings 
        ?GRATINGS - list of installed gratings, present specified with arrow

        TURRET - specific installed turret
        ?TURRET - get current

        INSTALL - install config for grating into non-volatile
            SELECT-GRATING
            G/MM
            BLAZE
            UNINSTALL

    Grating calibration:
        INIT-OFFSET: offset for designated grating
        INIT-GADJUST: adjustment value fo designated grating
            default: 10000 for all gratings
            limits: +/- 1000 for all gratings
        MONO-EESTATUS: return setup and grating calibration
        RESTORE FACTORY SETTINGS
        MONO-RESET after:
            INIT-OFFSET
            INIT-GADJUST    
        Defaults:
            TURRET: 1
            GRATNG: 1
            WAVELENGTH: 0.0nm
            SPEED: 100.0 nm/min
        

    Divert control - exit mirror, not needed
    Slit control - not needed





'''
import time

import serial

from pyopenlab.instrument.serial_instrument import SerialInstrument


class Acton(SerialInstrument):
    """Acton SP-2300i monochromator controlled over a serial connection."""

    port_settings = dict(
        baudrate=9600,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=5,  # wait at most one second for a response
        writeTimeout=1,  # similarly, fail if writing takes >1s
        xonxoff=False,
        rtscts=False,
        dsrdtr=False,
    )

    def __init__(self, port, debug=0, echo=True, dummy=False):
        """Open the monochromator on the given serial port and reset it.

        Args:
            port: Serial port name (e.g. "COM6").
            debug: If greater than 0, print diagnostic information.
            echo: True if the device echoes commands back (affects reply parsing).
            dummy: Accepted for API compatibility; currently unused.
        """
        if debug > 0:
            print("Started: Acton.__init__")
        SerialInstrument.__init__(self, port)
        self.echo = echo

        # self.ser.flushInput()
        # self.ser.flushOutput()

        # model info
        self.write_command("MONO-RESET")
        # if debug > 0:
        # print "Started [2]: Acton.__init__"

        # self.model = self.write_command("MODEL",debug=debug)
        # self.serial_number = self.write_command("SERIAL",debug=debug)
        # load grating info
        # self.read_grating_info(debug=debug)

    def read_done_status(self):
        """Return True if the monochromator has finished its current move."""
        resp = self.write_command("MONO-?DONE")  # returns either 1 or 0 for done or not done
        return bool(int(resp))

    def read_wl(self):
        """Read the present wavelength, caching it on ``self.wl``.

        Returns:
            The present wavelength in nm as a float.
        """
        resp = self.write_command("?NM")
        "700.000 nm"
        self.wl = float(resp.split()[0])
        return self.wl

#     def write_wl(self, wl, waittime=1.0):
#         wl = float(wl)
#         resp = self.write_command("%0.3f NM" % wl,waittime=waittime)
# #        if self.debug: logger.debug("write_wl wl:{} resp:{}".format( wl, resp))

    def write_wl_fast(self, wl, waittime=1.0):
        """Move to a destination wavelength at maximum motor speed.

        Args:
            wl: Destination wavelength in nm.
            waittime: Seconds to wait for the device to respond.
        """
        wl = float(wl)
        resp = self.write_command("%0.3f GOTO" % wl, waittime=waittime)
#        if self.debug: logger.debug("write_wl_fast wl:{} resp:{}".format( wl, resp))

#     def write_wl_nonblock(self, wl):
#         wl = float(wl)
#         resp = self.write_command("%0.3f >NM" % wl)
# #        if self.debug: logger.debug("write_wl_nonblock wl:{} resp:{}".format( wl, resp))

    def read_grating_info(self, debug=0):
        """Query installed gratings and cache them on the instance.

        Populates ``self.gratings`` (list of ``(number, name)`` tuples) and
        ``self.gratings_dict`` (number -> name).

        Args:
            debug: If greater than 0, print diagnostic information.

        Returns:
            The list of ``(number, name)`` grating tuples.
        """
        grating_string = self.write_command("?GRATINGS", waittime=1.0, debug=debug)
        """
            \x1a1  1200 g/mm BLZ=  500NM 
            2  300 g/mm BLZ=  1.0UM 
            3  150 g/mm BLZ=  500NM 
            4  Not Installed     
            5  Not Installed     
            6  Not Installed     
            7  Not Installed     
            8  Not Installed     
            9  Not Installed     
            ok
        """
        # 0x1A is the arrow char, indicates selected grating

        if self.echo:
            gratings = grating_string.splitlines()[1:-1]  # needed for echo
        else:
            gratings = grating_string.splitlines()[0:-1]  # for no echo


#        if self.debug: print(gratings)

        print(gratings)
        self.gratings = []

        for grating in gratings:
            #            if self.debug: logger.debug("grating: {}".format( grating ))
            grating_num, name = grating.strip('\x1a').strip(' ').split(' ', 1)
            #if self.debug: logger.debug("grating stripped: {}".format( grating ))
            num = int(grating_num)
            self.gratings.append((num, name))

        self.gratings_dict = {num: name for num, name in self.gratings}

        return self.gratings

    def set_wavelength(self, wavelength, blocking=True, fast=True, debug=0):
        """Move to a destination wavelength.

        Args:
            wavelength: Destination wavelength in nm.
            blocking: If True, move and wait; if False, issue a non-blocking
                move (">NM") that must be terminated with MONO-STOP.
            fast: When blocking, True uses GOTO (max speed) and False uses NM
                (the configured scan rate). Ignored when ``blocking`` is False.
            debug: If greater than 0, print diagnostic information.

        Returns:
            The device's reply to the move command.
        """
        if blocking == True:

            if fast == False:
                query = "{0:.3f} NM".format(wavelength)
            elif fast == True:
                query = "{0:.3f} GOTO".format(wavelength)

        elif blocking == False:
            query = "{0:.3f} >NM".format(wavelength)
        print("set_wavelength:", query)
        resp = self.write_command(query, debug=debug)
        return resp

    def get_wavelength(self):
        """Return the raw "?NM" reply (wavelength in nm with units appended)."""
        resp = self.write_command("?NM")
        return resp

    def read_turret(self):
        """Read the active turret number, caching it on ``self.turret``.

        Returns:
            The current turret number as an int.
        """
        resp = self.write_command("?TURRET")
        self.turret = int(resp)
        return self.turret

    def write_turret(self, turret):
        """Validate a turret number (1-3).

        Args:
            turret: Turret number, must be 1, 2 or 3.

        Note:
            This does not actually send a TURRET command; the command string is
            built but never written. Left unfixed per the surgical-changes policy.
        """
        assert turret in [1, 2, 3]
        "%i TURRET"

    def read_grating(self):
        """Read the active grating number, caching it on ``self.grating``.

        Returns:
            The current grating number as an int.
        """
        resp = self.write_command("?GRATING")
        self.grating = int(resp)
        return self.grating

    def read_grating_name(self):
        """Return the ``(number, name)`` tuple for the current grating.

        Returns:
            The grating tuple for the active grating.

        Note:
            Relies on ``self.gratings``, which is only populated by
            :meth:`read_grating_info`; if that has not been called this raises
            ``AttributeError``.
        """
        self.read_grating()
        return self.gratings[self.grating - 1]

    def set_grating(self, grating):
        """Select a grating.

        Args:
            grating: Grating number, must satisfy 0 < grating < 10.
        """
        assert 0 < grating < 10
        self.write_command("%i GRATING" % grating)

    def read_exit_mirror(self):
        """Read the exit mirror position, caching it on ``self.exit_mirror``.

        Returns:
            The exit mirror position as an upper-case string.
        """
        resp = self.write_command("EXIT-MIRROR ?MIRROR")
        self.exit_mirror = resp.upper()
        return self.exit_mirror

    def write_exit_mirror(self, pos):
        """Set the exit mirror position.

        Args:
            pos: Target position, 'FRONT' or 'SIDE' (case-insensitive).
        """
        pos = pos.upper()
        assert pos in ['FRONT', 'SIDE']
        self.write_command("EXIT-MIRROR %s" % pos)

    def read_entrance_slit(self):
        """Read the entrance slit width, caching it on ``self.entrance_slit``.

        Returns:
            The slit width in microns, or -1 if no slit motor is fitted.
        """
        resp = self.write_command("SIDE-ENT-SLIT ?MICRONS")
        #"480 um" or "no motor"
        print((repr(resp)))
        if resp == 'no motor':
            self.entrance_slit = -1
        else:
            self.entrance_slit = int(resp.split()[0])
        return self.entrance_slit

    def write_entrance_slit(self, pos):
        """Set the entrance slit width.

        Args:
            pos: Slit width in microns, must satisfy 5 <= pos <= 3000.
        """
        assert 5 <= pos <= 3000
        self.write_command("SIDE-ENT-SLIT %i MICRONS" % pos)
        # should return new pos

    def home_entrance_slit(self):
        """Home the entrance slit.

        Note:
            Not implemented; the SHOME command string is present but never sent.
        """
        # TODO
        "SIDE-ENT-SLIT SHOME"

    def read_exit_slit(self):
        """Read the exit slit width, caching it on ``self.exit_slit``.

        Returns:
            The slit width in microns, or -1 if no slit motor is fitted.
        """
        resp = self.write_command("SIDE-EXIT-SLIT ?MICRONS")
        #"960 um" or "no motor"
        if resp == 'no motor':
            self.exit_slit = -1
        else:
            self.exit_slit = int(resp.split()[0])
        return self.exit_slit

    def write_exit_slit(self, pos):
        """Set the exit slit width.

        Args:
            pos: Slit width in microns, must satisfy 5 <= pos <= 3000.
        """
        assert 5 <= pos <= 3000
        self.write_command("SIDE-EXIT-SLIT %i MICRONS" % pos)

    def write_command(self, cmd, waittime=0.5, debug=0):
        """Send a command and read the reply up to the terminating "ok".

        Args:
            cmd: ASCII command string (a carriage return is appended).
            waittime: Seconds to wait after writing before reading.
            debug: If greater than 0, print the full and tail of the response.

        Returns:
            The response text with the echoed command stripped when ``self.echo``
            is True, otherwise the full response. Returns 0 if reading times out
            more than three times.
        """
        cmd_bytes = (cmd).encode('ASCII')
        self.ser.write(cmd_bytes + b"\r")
        time.sleep(waittime)

        out = bytearray()
        char = b""
        missed_char_count = 0
        while char != b"k":
            char = self.ser.read()
            if char == b"":  #handles a timeout here
                missed_char_count += 1
                if missed_char_count > 3:
                    return 0
                continue
            out += char

        out += self.ser.read(2)  #Should be "\r\n"

        out = out.decode('ascii')

        if debug > 0:
            print("response full:", out)
            print("response tail:", out[-5:])
        # assert out[-5:] == " ok\r\n"
        # out = out[:-5].strip()

        # When echo is enabled, verify echoed command and strip
        if self.echo:
            echo = out[0:len(cmd_bytes)]
            rest = out[len(cmd_bytes):]
            print(("echo, rest, cmd:", echo, rest, cmd_bytes))
            # assert echo == cmd
            return rest
        else:
            return out
        #self.ser.flushInput()
        #self.ser.flushOutput()
        #return out

    def close(self):
        """Close the underlying serial connection."""
        self.ser.close()

if __name__ == "__main__":

    port = "COM6"
    ac = Acton(port=port)
