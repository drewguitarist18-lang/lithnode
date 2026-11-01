; The one-click window: no wizard pages, just a small dark rounded window with the crab, an Install button and a thin
; progress bar, then Lithnode opens. Inno's own wizard still runs underneath (welcome -> installing -> done); its
; controls are hidden and these are drawn over it. Included by setup.iss; art from make_icon.py (installer\oneclick).

[Files]
Source: "oneclick\*.png"; Flags: dontcopy

[Code]
const
  WIN_W = 440; WIN_H = 300;
  C_BG = $100E0E;          { #0E0E10, as BGR }
  C_INK = $E6EBEC;         { #ECEBE6 }
  C_SOFT = $878C8D;        { #8D8C87 }
  C_TRACK = $2B2626;       { #26262B }
  C_EDGE = $2E2A2A;        { #2A2A2E }

var
  Crab, Pill, Track, Fill: TBitmapImage;
  Back: TLabel;
  Title, Sub, PillText, CloseX, Status, Percent: TLabel;
  PetBox: TNewCheckBox;
  WantPetChoice: Boolean;
  WizW, WizH, NextLeft, BackLeft, CancelLeft: Integer;

function DwmSetWindowAttribute(hwnd: HWND; attr: DWORD; var value: Integer; size: DWORD): HRESULT;
  external 'DwmSetWindowAttribute@dwmapi.dll stdcall delayload';
function CreateRoundRectRgn(x1, y1, x2, y2, w, h: Integer): THandle;
  external 'CreateRoundRectRgn@gdi32.dll stdcall';
function SetWindowRgn(hwnd: HWND; rgn: THandle; redraw: BOOL): Integer;
  external 'SetWindowRgn@user32.dll stdcall';
function ReleaseCapture: BOOL; external 'ReleaseCapture@user32.dll stdcall';
function GetSystemMetrics(index: Integer): Integer; external 'GetSystemMetrics@user32.dll stdcall';

function WantPet: Boolean;
begin
  Result := WantPetChoice;
end;

{ the art comes in a few sizes so the pixels stay whole at any display scale }
function ArtFile(Kind: String): String;
var
  Pct, Best: Integer;
begin
  Pct := ScaleX(100);
  if Pct >= 275 then Best := 300 else if Pct >= 225 then Best := 250 else if Pct >= 188 then Best := 200
  else if Pct >= 163 then Best := 175 else if Pct >= 138 then Best := 150 else if Pct >= 113 then Best := 125
  else Best := 100;
  Result := Kind + '-' + IntToStr(Best) + '.png';
  ExtractTemporaryFile(Result);
  Result := ExpandConstant('{tmp}\') + Result;
end;

function UiFont: String;
begin
  if FontExists('Segoe UI Variable Display') then Result := 'Segoe UI Variable Display' else Result := 'Segoe UI';
end;

function NewLabel(Text: String; Size: Integer; Color: TColor; Bold: Boolean): TLabel;
begin
  Result := TLabel.Create(WizardForm);
  Result.Parent := WizardForm;
  Result.StyleElements := Result.StyleElements - [seFont, seClient];
  Result.Transparent := True;
  Result.AutoSize := False;
  Result.Font.Name := UiFont;
  Result.Font.Size := Size;
  Result.Font.Color := Color;
  if Bold then Result.Font.Style := [fsBold];
  Result.Caption := Text;
end;

function NewImage(FileName: String): TBitmapImage;
begin
  Result := TBitmapImage.Create(WizardForm);
  Result.Parent := WizardForm;
  Result.BackColor := clNone;
  if FileName <> '' then begin
    Result.AutoSize := True;
    Result.PngImage.LoadFromFile(FileName);
  end;
end;

function NewBar(Color: TColor): TBitmapImage;
begin
  Result := TBitmapImage.Create(WizardForm);
  Result.Parent := WizardForm;
  Result.BackColor := Color;
end;

{ a borderless window still moves when you drag it anywhere }
procedure DragWindow(Sender: TObject; Button: TMouseButton; Shift: TShiftState; X, Y: Integer);
begin
  if Button = mbLeft then begin
    ReleaseCapture;
    SendMessage(WizardForm.Handle, $00A1 { WM_NCLBUTTONDOWN }, 2 { HTCAPTION }, 0);
  end;
end;

procedure HideWizard;
begin
  WizardForm.OuterNotebook.Visible := False;
  WizardForm.Bevel.Visible := False;
  { pushed off the window rather than hidden: Inno still clicks Next for us }
  WizardForm.NextButton.Left := -1000;
  WizardForm.BackButton.Left := -1000;
  WizardForm.CancelButton.Left := -1000;
end;

{ a page the one-click window doesn't draw (a file in use, a restart needed): show Inno's own wizard for it }
procedure ShowWizard;
var
  I: Integer;
begin
  for I := 0 to WizardForm.ControlCount - 1 do
    if (WizardForm.Controls[I] is TLabel) or (WizardForm.Controls[I] is TBitmapImage) or (WizardForm.Controls[I] = PetBox) then
      WizardForm.Controls[I].Visible := False;
  WizardForm.BorderStyle := bsSingle;
  WizardForm.ClientWidth := WizW; WizardForm.ClientHeight := WizH;
  WizardForm.OuterNotebook.Visible := True;
  WizardForm.Bevel.Visible := True;
  WizardForm.NextButton.Left := NextLeft;
  WizardForm.BackButton.Left := BackLeft;
  WizardForm.CancelButton.Left := CancelLeft;
end;

{ an update: close the Lithnode that's running from the install folder, so its files can be replaced }
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
  App: String;
begin
  App := ExpandConstant('{app}');
  StringChangeEx(App, '''', '''''', True);
  Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    { CIM, not Get-Process: setup is 32-bit and can't read a 64-bit process's path }
    '-NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -like ''' + App + '\*'' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"',
    '', SW_HIDE, ewWaitUntilTerminated, Code);
  Result := '';
end;

procedure InstallClick(Sender: TObject);
begin
  WantPetChoice := PetBox.Checked;
  WizardForm.NextButton.OnClick(WizardForm.NextButton);
end;

procedure CloseClick(Sender: TObject);
begin
  WizardForm.Close;
end;

procedure CancelButtonClick(CurPageID: Integer; var Cancel, Confirm: Boolean);
begin
  Confirm := False;   { the window's own x means it: no "are you sure" box }
end;

procedure RoundCorners;
var
  Pref: Integer;
begin
  Pref := 2;   { DWMWCP_ROUND: Windows 11's own smooth corners }
  if DwmSetWindowAttribute(WizardForm.Handle, 33, Pref, 4) <> 0 then
    SetWindowRgn(WizardForm.Handle, CreateRoundRectRgn(0, 0, WizardForm.Width + 1, WizardForm.Height + 1, ScaleX(16), ScaleX(16)), True)
  else begin
    Pref := C_EDGE;   { a hairline edge so the dark window doesn't melt into a dark desktop }
    DwmSetWindowAttribute(WizardForm.Handle, 34, Pref, 4);
  end;
end;

procedure InitializeWizard;
var
  W, H, PillW, PillH: Integer;
begin
  WantPetChoice := True;
  WizW := WizardForm.ClientWidth; WizH := WizardForm.ClientHeight;
  NextLeft := WizardForm.NextButton.Left; BackLeft := WizardForm.BackButton.Left;
  CancelLeft := WizardForm.CancelButton.Left;
  W := ScaleX(WIN_W); H := ScaleY(WIN_H);
  WizardForm.BorderStyle := bsNone;
  WizardForm.Color := C_BG;
  WizardForm.StyleElements := WizardForm.StyleElements - [seClient];
  WizardForm.ClientWidth := W; WizardForm.ClientHeight := H;
  HideWizard;
  Back := NewLabel('', 9, C_INK, False);   { the window's face: drag it anywhere to move the window }
  Back.SetBounds(0, 0, W, H);
  Back.OnMouseDown := @DragWindow;

  CloseX := NewLabel(#$2715, 11, C_SOFT, False);
  if FontExists('Segoe Fluent Icons') then begin CloseX.Font.Name := 'Segoe Fluent Icons'; CloseX.Font.Size := 9; CloseX.Caption := #$E8BB; end;
  CloseX.Alignment := taCenter; CloseX.Layout := tlCenter;
  CloseX.SetBounds(W - ScaleX(42), ScaleY(10), ScaleX(32), ScaleY(32));
  CloseX.Cursor := crHand; CloseX.OnClick := @CloseClick;

  Crab := NewImage(ArtFile('crab'));
  Crab.Left := (W - Crab.Width) div 2; Crab.Top := ScaleY(48);

  Title := NewLabel('Lithnode', 20, C_INK, True);
  Title.Alignment := taCenter;
  Title.SetBounds(0, ScaleY(130), W, ScaleY(40));
  Title.OnMouseDown := @DragWindow;
  Sub := NewLabel('Your AI team, managed.', 10, C_SOFT, False);
  Sub.Alignment := taCenter;
  Sub.SetBounds(0, ScaleY(170), W, ScaleY(24));
  Sub.OnMouseDown := @DragWindow;

  PetBox := TNewCheckBox.Create(WizardForm);
  PetBox.Parent := WizardForm;
  PetBox.Caption := 'Add Claude Pet to the desktop';
  PetBox.Font.Name := UiFont; PetBox.Font.Size := 9;
  PetBox.Checked := True;
  PetBox.SetBounds(ScaleX(28), ScaleY(240), ScaleX(230), ScaleY(22));

  Pill := NewImage(ArtFile('pill'));
  PillW := Pill.Width; PillH := Pill.Height;
  Pill.Left := W - ScaleX(28) - PillW; Pill.Top := ScaleY(231);
  Pill.Cursor := crHand; Pill.OnClick := @InstallClick;
  PillText := NewLabel('Install', 10, C_BG, True);
  PillText.Alignment := taCenter; PillText.Layout := tlCenter;
  PillText.SetBounds(Pill.Left, Pill.Top, PillW, PillH);
  PillText.Cursor := crHand; PillText.OnClick := @InstallClick;

  Status := NewLabel('Installing' + #$2026, 10, C_INK, False);
  Status.SetBounds(ScaleX(28), ScaleY(222), ScaleX(300), ScaleY(24));
  Percent := NewLabel('0%', 10, C_SOFT, False);
  Percent.Alignment := taRightJustify;
  Percent.SetBounds(W - ScaleX(28) - ScaleX(80), ScaleY(222), ScaleX(80), ScaleY(24));
  Track := NewBar(C_TRACK);
  Track.SetBounds(ScaleX(28), ScaleY(254), W - ScaleX(56), ScaleY(4));
  Fill := NewBar(C_INK);
  Fill.SetBounds(ScaleX(28), ScaleY(254), 0, ScaleY(4));
  Status.Visible := False; Percent.Visible := False; Track.Visible := False; Fill.Visible := False;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID <> wpWelcome) and (CurPageID <> wpReady) and (CurPageID <> wpPreparing) and (CurPageID <> wpInstalling) then begin
    ShowWizard;
    Exit;
  end;
  HideWizard;
  if CurPageID = wpPreparing then Status.Caption := 'Getting ready' + #$2026
  else Status.Caption := 'Installing' + #$2026;
  if (CurPageID = wpWelcome) or (CurPageID = wpReady) then begin
    WizardForm.Left := (GetSystemMetrics(0) - WizardForm.Width) div 2;
    WizardForm.Top := (GetSystemMetrics(1) - WizardForm.Height) div 2;
    RoundCorners;
  end;
  if (CurPageID = wpPreparing) or (CurPageID = wpInstalling) then begin
    PetBox.Visible := False; Pill.Visible := False; PillText.Visible := False; CloseX.Visible := False;
    Status.Visible := True; Percent.Visible := True; Track.Visible := True; Fill.Visible := True;
  end;
end;

procedure CurInstallProgressChanged(CurProgress, MaxProgress: Integer);
begin
  if MaxProgress <= 0 then Exit;
  Fill.Width := MulDiv(Track.Width, CurProgress, MaxProgress);
  Percent.Caption := IntToStr(MulDiv(100, CurProgress, MaxProgress)) + '%';
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then begin
    Fill.Width := Track.Width;
    Percent.Caption := '100%';
    Status.Caption := 'Opening Lithnode' + #$2026;
    WizardForm.Repaint;
  end;
end;
