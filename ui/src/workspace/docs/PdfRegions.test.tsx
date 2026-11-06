import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PdfRegions } from './PdfRegions';

 describe('PDF page coordinates', () => {
  for (const width of [600, 1400]) for (const direction of ['ltr', 'rtl']) {
    it(`draws and drags at ${width} in ${direction}`, () => {
      const selected = vi.fn();
      const { container } = render(<div dir={direction}><PdfRegions width={600} height={800} boxes={[[60, 80, 180, 160]]} onSelect={selected}><img alt="Sample PDF" style={{width}} /></PdfRegions></div>);
      const overlay = screen.getByTestId('pdf-regions');
      expect(overlay).toHaveAttribute('viewBox', '0 0 600 800');
      const box = container.querySelector('rect')!;
      expect(box).toHaveAttribute('x', '60');
      expect(box).toHaveAttribute('y', '80');
      expect(box).toHaveAttribute('width', '120');
      vi.spyOn(overlay, 'getBoundingClientRect').mockReturnValue({left: 30, top: 40, width, height: width * 800 / 600} as DOMRect);
      fireEvent.pointerDown(overlay, {clientX: 30 + width * .3, clientY: 40 + width * .4, pointerId: 1, button: 0});
      fireEvent.pointerUp(overlay, {clientX: 30 + width * .1, clientY: 40 + width * .1, pointerId: 1});
      expect(selected).toHaveBeenCalledWith([60, 60, 180, 240]);
    });
  }
});
